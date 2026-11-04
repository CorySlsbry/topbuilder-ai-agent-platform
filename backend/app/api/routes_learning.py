"""Self-learning GOVERNANCE API (Phase C/D): the human approval queue + golden-set + drift + tuning.

A candidate learned rule only goes ACTIVE here — and approval runs the eval gate first, so a human
can't promote a rule that fails the golden set / safety check / ADR-0003 invariant (unless they
explicitly force it). Reads are restricted to the leadership/operator tier (require_unrestricted —
a department-scoped login can't browse governance); promotions/mutations are admin-only.
"""
from __future__ import annotations

import hmac
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import get_principal, require_admin, require_unrestricted
from app.config import get_settings
from app.db import tenant_session
from app.learning import consolidation, eval_harness
from app.repositories import governance as gov
from app.security import Principal

router = APIRouter(prefix="/v1/learning", tags=["learning"])

AGENTS = ("workforce", "financial", "inventory", "booking", "routing", "documents")


class ApproveIn(BaseModel):
    rollout_pct: int = 100      # canary: start < 100 to ramp a new rule gradually
    force: bool = False         # override a failing eval gate (admin's call, audited by reviewed_by)


class RolloutIn(BaseModel):
    rollout_pct: int


class GoldenIn(BaseModel):
    agent: str
    situation_text: str
    must_include: list[str] = []
    must_avoid: list[str] = []
    note: str | None = None


class ParamIn(BaseModel):
    value: float
    agent: str


# --- Preference approval queue --------------------------------------------------------------------
@router.get("/preferences")
async def list_preferences(
    agent: str | None = Query(None), status_filter: str | None = Query(None, alias="status"),
    principal: Principal = Depends(require_unrestricted),
) -> list[dict]:
    async with tenant_session(principal.tenant_id) as s:
        return await gov.list_preferences(s, agent=agent, status=status_filter)


@router.get("/preferences/{preference_id}/evals")
async def list_evals(preference_id: uuid.UUID, principal: Principal = Depends(require_unrestricted)) -> list[dict]:
    async with tenant_session(principal.tenant_id) as s:
        return await gov.list_eval_runs(s, preference_id=preference_id)


@router.post("/preferences/{preference_id}/approve")
async def approve(
    preference_id: uuid.UUID, body: ApproveIn, principal: Principal = Depends(require_admin)
) -> dict:
    """Promote a candidate to ACTIVE — but only if it clears the eval gate (or force=true)."""
    async with tenant_session(principal.tenant_id) as s:
        pref = await gov.get_preference(s, preference_id=preference_id)
        if pref is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "preference not found")
        if pref["status"] != "candidate":
            raise HTTPException(status.HTTP_409_CONFLICT, f"not a candidate (status={pref['status']})")
        ev = await eval_harness.evaluate_candidate(s, preference=pref)
        if ev["verdict"] != "pass" and not body.force:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={"message": "eval gate failed", "eval": ev},
            )
        approved = await gov.approve_preference(
            s, preference_id=preference_id, reviewed_by=principal.user_id, rollout_pct=body.rollout_pct
        )
        return {"preference": approved, "eval": ev, "forced": body.force and ev["verdict"] != "pass"}


@router.post("/preferences/{preference_id}/reject")
async def reject(preference_id: uuid.UUID, principal: Principal = Depends(require_admin)) -> dict:
    async with tenant_session(principal.tenant_id) as s:
        row = await gov.reject_preference(s, preference_id=preference_id, reviewed_by=principal.user_id)
        if row is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "not a candidate/quarantined preference")
        return row


@router.post("/preferences/{preference_id}/retire")
async def retire(preference_id: uuid.UUID, principal: Principal = Depends(require_admin)) -> dict:
    async with tenant_session(principal.tenant_id) as s:
        row = await gov.retire_preference(s, preference_id=preference_id, reviewed_by=principal.user_id)
        if row is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "not an active preference")
        return row


@router.put("/preferences/{preference_id}/rollout")
async def set_rollout(
    preference_id: uuid.UUID, body: RolloutIn, principal: Principal = Depends(require_admin)
) -> dict:
    async with tenant_session(principal.tenant_id) as s:
        row = await gov.set_rollout(s, preference_id=preference_id, rollout_pct=body.rollout_pct)
        if row is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "not an active preference")
        return row


# --- Golden set -----------------------------------------------------------------------------------
@router.get("/golden")
async def list_golden(agent: str | None = Query(None), principal: Principal = Depends(require_unrestricted)) -> list[dict]:
    async with tenant_session(principal.tenant_id) as s:
        return await gov.list_golden(s, agent=agent)


@router.post("/golden", status_code=status.HTTP_201_CREATED)
async def create_golden(body: GoldenIn, principal: Principal = Depends(require_admin)) -> dict:
    async with tenant_session(principal.tenant_id) as s:
        return await gov.insert_golden(
            s, agent=body.agent, situation_text=body.situation_text,
            must_include=body.must_include, must_avoid=body.must_avoid, note=body.note,
            created_by=principal.user_id,
        )


@router.delete("/golden/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_golden(case_id: uuid.UUID, principal: Principal = Depends(require_admin)) -> None:
    async with tenant_session(principal.tenant_id) as s:
        await gov.delete_golden(s, case_id=case_id)


# --- Drift + params -------------------------------------------------------------------------------
@router.get("/drift")
async def drift(agent: str | None = Query(None), principal: Principal = Depends(require_unrestricted)) -> list[dict]:
    async with tenant_session(principal.tenant_id) as s:
        return await gov.list_drift(s, agent=agent)


@router.get("/params")
async def list_params(principal: Principal = Depends(require_unrestricted)) -> list[dict]:
    async with tenant_session(principal.tenant_id) as s:
        return await gov.list_params(s)


@router.put("/params/{name}")
async def set_param(name: str, body: ParamIn, principal: Principal = Depends(require_admin)) -> dict:
    async with tenant_session(principal.tenant_id) as s:
        return await gov.set_param(s, name=name, value=body.value, agent=body.agent, updated_by=principal.user_id)


# --- Consolidation trigger (the nightly job, on-demand) -------------------------------------------
@router.post("/consolidate")
async def run_consolidation(
    agent: str | None = Query(None), principal: Principal = Depends(require_admin)
) -> dict:
    """Run the nightly consolidation now (one agent, or all six). Admin-only."""
    targets = [agent] if agent else list(AGENTS)
    reports = []
    for a in targets:
        async with tenant_session(principal.tenant_id) as s:
            reports.append(await consolidation.consolidate(s, agent=a))
    return {"reports": reports}


@router.post("/cron/consolidate")
async def cron_consolidate(x_cron_key: str | None = Header(default=None, alias="X-Cron-Key")) -> dict:
    """Scheduler entrypoint: run consolidation for every tenant × agent. Machine-auth via a shared
    secret header (not a user JWT), so a scheduled job needs no expiring token. 404 when not configured.

    Demo: iterates the seeded demo tenants. In production this enumerates tenants via an admin
    connection (the `tenants` table is RLS-protected from `app_user`)."""
    settings = get_settings()
    if not settings.cron_secret:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cron not configured")
    if not x_cron_key or not hmac.compare_digest(x_cron_key, settings.cron_secret):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "bad cron key")

    from app.demo import DEMO_TENANTS

    flagged: list[str] = []
    ran = 0
    for dt in DEMO_TENANTS.values():
        for a in AGENTS:
            async with tenant_session(dt.tenant_id) as s:
                rep = await consolidation.consolidate(s, agent=a)
                ran += 1
                if (rep.get("drift") or {}).get("flagged"):
                    flagged.append(f"{dt.slug}/{a}")
    return {"ran": ran, "tenants": len(DEMO_TENANTS), "agents": len(AGENTS), "flagged": flagged}
