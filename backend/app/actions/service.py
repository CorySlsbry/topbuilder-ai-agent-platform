"""Orchestration for human-approved actions (ADR 0007): propose -> approve -> execute.

Each step is tenant-scoped and audited. Execution is split into claim (a committed `executing` guard) →
external write (outside any DB transaction) → record, so we never hold a transaction open across an
upstream call, and a retry of an already-executed action is idempotent.
"""
from __future__ import annotations

import hashlib
import json
import uuid

from app.actions import executors
from app.actions.executors import ActionError, is_executable_kind
from app.actions.ownership import derive_owning_agent
from app.actions.schemas import ActionOut, PolicyOut, ProposeActionIn
from app.config import get_settings
from app.db import tenant_session
from app.org import permissions
from app.repositories import actions, policies, runs
from app.security import SYSTEM_ROLE, Principal

# Roles that may APPROVE/EXECUTE/UNDO a write (per-employee approval). A department 'lead' approves
# within their own department (incl. money/legal); an 'admin'/operator is unrestricted. A plain
# 'analyst' runner may PROPOSE but never approve. The SYSTEM_ROLE (the sync principal, ADR 0010) is
# refused above every transition and is intentionally absent here.
APPROVER_ROLES = {"lead", "admin"}


class ActionNotFound(Exception):
    pass


class ActionForbidden(Exception):
    """The caller's identity may not perform this transition (e.g. the propose-only system principal
    trying to approve/execute). A human principal must approve and execute."""


class ActionConflict(Exception):
    """The action is not in a state that permits this transition."""


class ActionDisabled(Exception):
    """Execution is disabled by policy (master switch off, or kind not allowlisted)."""


class ActionExecutionError(Exception):
    """The executor (the upstream write) failed."""


# Kinds that must ALWAYS stay human-in-the-loop, even when the agent is in 'auto' mode. Each is a
# legally- or financially-consequential write where a person must consent before it fires:
#   - payroll_adjustment      — writes someone's pay; a wrong figure mis-pays a worker.
#   - place_dunning_call /
#     send_dunning_sms /
#     send_dunning_email       — outbound customer contact under TCPA / CASL / quiet-hours rules;
#                                an auto-dialed or auto-texted collection is a real compliance event.
#   - create_ap_draft          — posts an accounts-payable entry to the books (money).
#   - register_warranty        — acts inside a human-established vendor session; never unattended.
#   - update_pricebook_item    — writes a customer-facing PRICE; a wrong figure misprices every job
#                                quoted from it. A human confirms the recomputed price before it lands.
#   - ads.create_campaign /
#     ads.update_budget /
#     ads.activate_campaign    — commit ad SPEND (create a funded campaign, raise a budget, or flip a
#                                campaign live). A person must consent before money goes out the door.
#                                ads.pause_campaign (spend-REDUCING) and ads.sync_conversion (an
#                                idempotent, already-hashed upload) are deliberately NOT here — safe to
#                                auto-execute.
# Auto-mode still QUEUES these (proposed) for a human to approve; it just won't self-execute them.
ALWAYS_HITL_KINDS = {
    "payroll_adjustment",
    "place_dunning_call",
    "send_dunning_sms",
    "send_dunning_email",
    "create_ap_draft",
    "register_warranty",
    "update_pricebook_item",
    "ads.create_campaign",
    "ads.update_budget",
    "ads.activate_campaign",
}


def authorize_approver(principal: Principal, action: dict) -> None:
    """Authorize a human to approve/execute/undo/reject a STORED action (per-employee approval, PURE).

    Two rules, both keyed on the action's OWNING agent (``KIND_OWNER`` — never the spoofable stored
    ``agent``), reusing the exact department predicate ``propose`` already enforces:
      1. department scope — the approver's department must include the owning agent (admin = unrestricted);
      2. money/legal — an ``ALWAYS_HITL_KINDS`` write additionally requires a department LEAD (or admin),
         so a plain in-department analyst can propose but cannot approve a pay/AP/dunning/price/ad write.
    The SYSTEM_ROLE refusal lives in each caller, ABOVE this, so the sync principal never reaches here.
    Raises ``ActionForbidden`` (-> HTTP 403) on a violation.
    """
    owning_agent = derive_owning_agent(action["kind"], action["agent"])
    if not permissions.can_use_agent(principal.role, principal.department, owning_agent):
        raise ActionForbidden(
            f"department '{principal.department}' does not include the {owning_agent} agent for this action"
        )
    if action["kind"] in ALWAYS_HITL_KINDS and principal.role not in APPROVER_ROLES:
        raise ActionForbidden(
            f"action kind '{action['kind']}' is money/legal and requires a department-lead approver"
        )


def _idempotency_key(kind: str, run_id: uuid.UUID | None, params: dict, provided: str | None) -> str:
    if provided:
        return provided
    natural = params.get("intake_id") or params.get("id")
    if natural:
        return f"{kind}:{run_id or '-'}:{natural}"
    blob = json.dumps({"kind": kind, "run_id": str(run_id), "params": params}, sort_keys=True, default=str)
    return f"{kind}:{hashlib.sha256(blob.encode('utf-8')).hexdigest()[:24]}"


async def propose_action(principal: Principal, payload: ProposeActionIn) -> ActionOut:
    settings = get_settings()
    key = _idempotency_key(payload.kind, payload.run_id, payload.params, payload.idempotency_key)
    async with tenant_session(principal.tenant_id) as session:
        action_id = uuid.uuid4()
        row = await actions.insert_action(
            session,
            action_id=action_id,
            run_id=payload.run_id,
            agent=payload.agent,
            kind=payload.kind,
            params=payload.params,
            idempotency_key=key,
            requested_by=principal.user_id,
        )
        if row is None:  # idempotent: an identical action was already proposed
            row = await actions.get_action_by_key(session, idempotency_key=key)
            if row is not None and row["status"] in ("undone", "failed"):
                # A dead action must not block a redo: tombstone its key, propose fresh.
                dead_id = row["id"]
                await actions.release_idempotency_key(
                    session, action_id=dead_id, new_key=f"{key}::{row['status']}::{dead_id}"
                )
                row = await actions.insert_action(
                    session,
                    action_id=action_id,
                    run_id=payload.run_id,
                    agent=payload.agent,
                    kind=payload.kind,
                    params=payload.params,
                    idempotency_key=key,
                    requested_by=principal.user_id,
                )
                await runs.insert_audit(
                    session,
                    actor=str(principal.user_id),
                    action="action.propose",
                    target=str(action_id),
                    detail={"agent": payload.agent, "kind": payload.kind,
                            "idempotency_key": key, "supersedes": str(dead_id)},
                )
        else:
            await runs.insert_audit(
                session,
                actor=str(principal.user_id),
                action="action.propose",
                target=str(action_id),
                detail={"agent": payload.agent, "kind": payload.kind, "idempotency_key": key},
            )
        mode = await policies.get_mode(session, agent=payload.agent)

    # Autonomous-with-undo: an 'auto' agent approves + executes its own proposal immediately.
    # The propose-only system principal (event-detection loop, ADR 0010) is excluded — a detected
    # event is always left proposed for a human, so the loop is approve-first regardless of mode.
    if (
        row is not None
        and row["status"] == "proposed"
        and mode == "auto"
        and principal.role != SYSTEM_ROLE
        and settings.actions_enabled
        and payload.kind not in ALWAYS_HITL_KINDS
        and is_executable_kind(payload.kind, settings)
    ):
        try:
            await approve_action(principal, row["id"])
            return await execute_action(principal, row["id"])
        except (ActionConflict, ActionDisabled, ActionExecutionError):
            pass  # fall back to leaving it proposed for a human

    return ActionOut.from_row(row)  # type: ignore[arg-type]


async def approve_action(principal: Principal, action_id: uuid.UUID) -> ActionOut:
    if principal.role == SYSTEM_ROLE:
        raise ActionForbidden("the system principal may only propose; a human must approve")
    async with tenant_session(principal.tenant_id) as session:
        # Fetch BEFORE the transition so the per-id department/money-legal authz runs first (IDOR-safe):
        # a guarded UPDATE alone would let a dept-A lead approve a dept-B action by guessing its id.
        existing = await actions.get_action(session, action_id=action_id)
        if existing is None:
            raise ActionNotFound()
        authorize_approver(principal, existing)
        if existing["status"] == "approved":
            return ActionOut.from_row(existing)  # idempotent re-approve
        row = await actions.approve(session, action_id=action_id, approved_by=principal.user_id)
        if row is None:
            raise ActionConflict(f"cannot approve an action in status '{existing['status']}'")
        await runs.insert_audit(
            session,
            actor=str(principal.user_id),
            action="action.approve",
            target=str(action_id),
            detail={"kind": row["kind"]},
        )
    return ActionOut.from_row(row)


async def reject_action(principal: Principal, action_id: uuid.UUID, *, reason: str | None = None) -> ActionOut:
    """Disapprove a proposed action (proposed -> rejected). Same approver authorization as approve; the
    action is never executed. Idempotent; audited. The reason (if any) is recorded on the row."""
    if principal.role == SYSTEM_ROLE:
        raise ActionForbidden("the system principal may only propose; a human must decide")
    async with tenant_session(principal.tenant_id) as session:
        existing = await actions.get_action(session, action_id=action_id)
        if existing is None:
            raise ActionNotFound()
        authorize_approver(principal, existing)
        if existing["status"] == "rejected":
            return ActionOut.from_row(existing)  # idempotent
        row = await actions.reject(
            session, action_id=action_id, decided_by=principal.user_id, reason=reason
        )
        if row is None:
            raise ActionConflict(f"cannot disapprove an action in status '{existing['status']}'")
        await runs.insert_audit(
            session, actor=str(principal.user_id), action="action.reject", target=str(action_id),
            detail={"kind": row["kind"], "reason": reason},
        )
    return ActionOut.from_row(row)


async def execute_action(principal: Principal, action_id: uuid.UUID) -> ActionOut:
    if principal.role == SYSTEM_ROLE:
        raise ActionForbidden("the system principal may only propose; a human must execute")
    settings = get_settings()

    # Phase 1 — validate + claim (committed 'executing' guard).
    async with tenant_session(principal.tenant_id) as session:
        action = await actions.get_action(session, action_id=action_id)
        if action is None:
            raise ActionNotFound()
        authorize_approver(principal, action)  # dept + money/legal authz (execute is independently reachable)
        if action["status"] == "executed":
            return ActionOut.from_row(action)  # idempotent: already done
        mode = await policies.get_mode(session, agent=action["agent"])
        if mode == "off":
            raise ActionDisabled(f"agent '{action['agent']}' autonomy is off")
        if not settings.actions_enabled:
            raise ActionDisabled("action execution is disabled (set ACTIONS_ENABLED=true to opt in)")
        if not is_executable_kind(action["kind"], settings):
            raise ActionDisabled(f"action kind '{action['kind']}' is not enabled for execution")
        if action["status"] != "approved":
            raise ActionConflict(f"action must be 'approved' to execute (is '{action['status']}')")
        claimed = await actions.mark_executing(session, action_id=action_id)
        if claimed is None:
            raise ActionConflict("action is not in an executable state")

    # Phase 2 — the external write, outside any DB transaction.
    try:
        # Inject the row's TRUE tenant + action id server-side (** order: ours win) so an executor
        # that needs DB context can never be steered by proposer-supplied _tenant_id/_action_id.
        exec_params = {
            **claimed["params"],
            "_tenant_id": str(claimed["tenant_id"]),
            "_action_id": str(action_id),
        }
        result = await executors.execute(claimed["kind"], exec_params, settings)
    except Exception as exc:
        # ANY executor failure must fail the row, not leave it wedged in 'executing' forever.
        # ActionError is the clean, human-readable path; but an executor can also raise RuntimeError
        # (a fail-closed live client, an upstream >=300), an httpx network error, or a DBAPI error
        # (e.g. the executor reads its own tables and a migration isn't applied). All of them get the
        # same mark_failed + audit so the action is recoverable (failed, re-proposable), never stuck.
        reason = str(exc) if isinstance(exc, ActionError) else repr(exc)
        async with tenant_session(principal.tenant_id) as session:
            await actions.mark_failed(session, action_id=action_id, error=reason)
            await runs.insert_audit(
                session, actor=str(principal.user_id), action="action.execute.failed",
                target=str(action_id), detail={"error": reason, "kind": claimed["kind"]},
            )
        raise ActionExecutionError(reason) from exc

    # Phase 3 — record success + audit.
    async with tenant_session(principal.tenant_id) as session:
        row = await actions.mark_executed(session, action_id=action_id, result_payload=result)
        await runs.insert_audit(
            session, actor=str(principal.user_id), action="action.execute", target=str(action_id),
            detail={"kind": claimed["kind"], "external_ref": result.get("external_ref")},
        )
    return ActionOut.from_row(row)  # type: ignore[arg-type]


async def get_action(principal: Principal, action_id: uuid.UUID) -> ActionOut | None:
    async with tenant_session(principal.tenant_id) as session:
        row = await actions.get_action(session, action_id=action_id)
    return ActionOut.from_row(row) if row else None


async def list_actions(
    principal: Principal, *, agent: str | None = None, status: str | None = None, limit: int = 50
) -> list[ActionOut]:
    """Actions this principal may act on (the dept-scoped approvals queue). Admin/leadership
    (allowed_agents is None) sees all; a department-scoped principal sees ONLY actions whose OWNING
    agent (KIND_OWNER, not the stored agent) is in their department. The SQL agent-set is a cheap
    pre-filter; the Python pass is the AUTHORITATIVE filter (a stored agent can differ from the owner)."""
    allowed = permissions.allowed_agents(principal.role, principal.department)
    agents = None if allowed is None else sorted(allowed)
    async with tenant_session(principal.tenant_id) as session:
        rows = await actions.list_actions(session, agent=agent, agents=agents, status=status, limit=limit)
    if allowed is not None:
        rows = [
            r for r in rows
            if permissions.can_use_agent(
                principal.role, principal.department, derive_owning_agent(r["kind"], r["agent"])
            )
        ]
    return [ActionOut.from_row(r) for r in rows]


async def undo_action(principal: Principal, action_id: uuid.UUID) -> ActionOut:
    """Reverse an executed action (autonomous-with-undo). Idempotent; runs a compensation executor."""
    if principal.role == SYSTEM_ROLE:
        raise ActionForbidden("the system principal may only propose; a human must undo")
    settings = get_settings()
    async with tenant_session(principal.tenant_id) as session:
        action = await actions.get_action(session, action_id=action_id)
        if action is None:
            raise ActionNotFound()
        authorize_approver(principal, action)  # a lead may only undo within its own department
        if action["status"] == "undone":
            return ActionOut.from_row(action)  # idempotent
        if action["status"] != "executed":
            raise ActionConflict(f"only an 'executed' action can be undone (is '{action['status']}')")
        if not executors.is_undoable(action["kind"]):
            raise ActionConflict(f"action kind '{action['kind']}' is not undoable")

    try:
        reversal = await executors.undo(action["kind"], action["params"], action.get("result") or {}, settings)
    except ActionError as exc:
        raise ActionExecutionError(str(exc)) from exc

    async with tenant_session(principal.tenant_id) as session:
        row = await actions.mark_undone(session, action_id=action_id, undo_result=reversal)
        if row is None:  # lost a race — re-read
            row = await actions.get_action(session, action_id=action_id)
        await runs.insert_audit(
            session, actor=str(principal.user_id), action="action.undo", target=str(action_id),
            detail={"kind": action["kind"], "reversal": reversal.get("external_ref")},
        )
    return ActionOut.from_row(row)  # type: ignore[arg-type]


# --- per-agent autonomy policy (the switch for each agent) ----------------------------------
async def get_agent_policy(principal: Principal, agent: str) -> PolicyOut:
    async with tenant_session(principal.tenant_id) as session:
        mode = await policies.get_mode(session, agent=agent)
    return PolicyOut(agent=agent, mode=mode)


async def list_agent_policies(principal: Principal) -> list[PolicyOut]:
    async with tenant_session(principal.tenant_id) as session:
        rows = await policies.list_policies(session)
    return [PolicyOut(agent=r["agent"], mode=r["mode"], updated_at=r.get("updated_at")) for r in rows]


async def set_agent_policy(principal: Principal, agent: str, mode: str) -> PolicyOut:
    if mode not in policies.VALID_MODES:
        raise ActionConflict(f"invalid mode '{mode}'; must be one of {sorted(policies.VALID_MODES)}")
    async with tenant_session(principal.tenant_id) as session:
        row = await policies.upsert(session, agent=agent, mode=mode, updated_by=principal.user_id)
        await runs.insert_audit(
            session, actor=str(principal.user_id), action="agent.policy.set", target=agent,
            detail={"mode": mode},
        )
    return PolicyOut(agent=row["agent"], mode=row["mode"], updated_at=row.get("updated_at"))
