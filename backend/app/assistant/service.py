"""The in-app assistant: a Claude Sonnet 4.6 tool-use loop over a closed, permission-checked tool
registry (`tools.py`). Distinct from the deterministic agents — it drafts and does admin work; every
figure it can show comes verbatim from a tool that reads persisted agent results (ADR 0003). Every
chat message counts against a per-tenant daily cap (cost guardrail on the public demo)."""
from __future__ import annotations

import json
import uuid

from fastapi import HTTPException, status

from app.assistant import tools
from app.assistant.prompts import build_system_prompt
from app.config import get_settings
from app.db import tenant_session
from app.integrations.providers.registry import display_name
from app.repositories import assistant as assistant_repo
from app.repositories import communications as comms_repo
from app.repositories import runs
from app.repositories import tasks as tasks_repo
from app.repositories import tenant_settings as tenant_settings_repo
from app.security import Principal


def _dumps(value: object, limit: int = 6000) -> str:
    return tools.clip(json.dumps(value, default=str), limit)


async def _handle_tool(principal: Principal, name: str, args: dict) -> tuple[str, str | None]:
    """Execute one tool call -> (json result for the model, success summary or None).
    Refusals/validation failures return an error payload the model can relay — never an exception."""
    agent = str(args.get("agent", "")) if name == "get_agent_results" else None
    allowed, reason = tools.can_call(principal.role, principal.department, name, agent=agent)
    if allowed and tools.needs_operator_2fa(name, agent=agent) and principal.aal != "aal2":
        allowed, reason = False, (
            "this is an operator surface — it needs an admin sign-in with two-step verification"
        )
    if not allowed:
        return _dumps({"refused": reason}), None

    if name == "get_agent_results":
        async with tenant_session(principal.tenant_id) as session:
            result = await runs.get_latest_result(session, agent=agent)
        if result is None:
            return _dumps({"agent": agent, "result": None, "note": "this agent has not run yet"}), \
                f"Checked the {agent} agent (no run yet)"
        result.pop("reasoning_logs", None)
        return _dumps({"agent": agent, "result": result}), f"Read the {agent} agent's results"

    if name == "list_communications":
        try:
            limit = int(args.get("limit") or 15)
        except (TypeError, ValueError):
            limit = 15
        limit = max(1, min(limit, 25))
        async with tenant_session(principal.tenant_id) as session:
            rows = await comms_repo.list_(session)
        slim = [
            {"channel": r.get("channel"), "from": r.get("contact_name"),
             "subject": r.get("subject"), "agent_handled": r.get("agent_handled")}
            for r in rows[:limit]
        ]
        return _dumps({"communications": slim}), "Checked the inbox"

    if name == "list_tasks":
        status_f = args.get("status")
        async with tenant_session(principal.tenant_id) as session:
            rows = await tasks_repo.list_(session, status=status_f, limit=25)
        slim = [
            {"id": str(r.get("id")), "title": r.get("title"), "department": r.get("department"),
             "status": r.get("status"), "priority": r.get("priority")}
            for r in rows
        ]
        return _dumps({"tasks": slim}), "Checked the task list"

    if name == "create_task":
        clean, err = tools.validate_task(args)
        if err:
            return _dumps({"refused": err}), None
        async with tenant_session(principal.tenant_id) as session:
            row = await tasks_repo.insert(
                session, title=clean["title"], detail=clean["detail"],
                department=clean["department"], priority=clean["priority"],
                source_agent="assistant", related_ref=None, assignee_role=None,
            )
            await runs.insert_audit(
                session, actor=str(principal.user_id), action="assistant.create_task",
                target=str(row.get("id")), detail={"title": clean["title"]},
            )
        return _dumps({"created": {"id": str(row.get("id")), "title": clean["title"]}}), \
            f"Created task: {clean['title'][:60]}"

    if name == "list_email_workflows":
        async with tenant_session(principal.tenant_id) as session:
            result = await runs.get_latest_result(session, agent="email")
            overrides = await assistant_repo.list_email_overrides(session)
        by_id = {o["workflow_id"]: o for o in overrides}
        workflows = list((result or {}).get("workflows") or [])
        for w in workflows:
            o = by_id.pop(str(w.get("workflow_id")), None)
            if o:
                w["applied_rewrite"] = {
                    "subject": o["subject"], "preview": o["preview"],
                    "applied_by": o["updated_by"], "applied_at": str(o["updated_at"]),
                }
        payload = {
            "workflows": workflows,
            "note": None if result else "the email agent has not run yet — only applied overrides shown",
            "other_applied_overrides": list(by_id.values()) or None,
        }
        return _dumps(payload), "Reviewed the email workflows"

    if name == "update_email_workflow":
        clean, err = tools.validate_override(args)
        if err:
            return _dumps({"refused": err}), None
        # The id must belong to a workflow the email agent actually knows — an instruction smuggled
        # into inbox content can't aim this write at an arbitrary id (prompt-injection defusal; the
        # operator's explicit chat request is the ADR-0007 human approval for this change).
        async with tenant_session(principal.tenant_id) as vsession:
            latest = await runs.get_latest_result(vsession, agent="email")
        known = {str(w.get("workflow_id")) for w in (latest or {}).get("workflows") or []}
        if not known:
            return _dumps({"refused": "the email agent hasn't run yet — run it before changing workflows"}), None
        if clean["workflow_id"] not in known:
            return _dumps({"refused": f"unknown workflow_id; known: {sorted(known)}"}), None
        async with tenant_session(principal.tenant_id) as session:
            row = await assistant_repo.upsert_email_override(
                session, workflow_id=clean["workflow_id"], subject=clean["subject"],
                preview=clean["preview"], rationale=clean["rationale"],
                updated_by=principal.email or str(principal.user_id),
            )
            await runs.insert_audit(
                session, actor=str(principal.user_id), action="assistant.update_email_workflow",
                target=clean["workflow_id"],
                detail={"subject": clean["subject"], "preview": clean["preview"]},
            )
        return _dumps({"applied": row}), f"Updated workflow '{clean['workflow_id']}'"

    return _dumps({"refused": f"unknown tool '{name}'"}), None


async def _person_context(principal: Principal) -> tuple[str | None, str | None]:
    """Best-effort (name, title) from the org roster — never raises into the chat."""
    if not principal.person_id:
        return None, None
    try:
        from app.repositories import org as org_repo

        person = await org_repo.get_person(principal.tenant_id, uuid.UUID(principal.person_id))
        if isinstance(person, dict):
            p = person.get("person") if isinstance(person.get("person"), dict) else person
            return p.get("full_name"), p.get("title")
    except Exception:
        pass
    return None, None


async def chat(principal: Principal, raw_messages: list[dict], *, client_ip: str | None = None) -> dict:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "the assistant isn't configured on this deployment",
        )

    messages = tools.sanitize_history(raw_messages)
    if not messages:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "send at least one user message")

    # Cost guardrails (all DB-backed so they hold ACROSS Cloud Run instances): per-tenant/day, plus
    # a per-IP/day sub-cap (one abuser can't drain the demo) and a global/day ceiling (absolute spend
    # floor). One user message = one unit. Checked BEFORE the paid model call.
    from app.repositories import usage as usage_repo

    async with tenant_session(principal.tenant_id) as session:
        used = await assistant_repo.increment_usage(session)
        global_used = await usage_repo.bump_global(session, bucket="assistant_global")
        ip_used = (
            await usage_repo.bump_global(session, bucket=f"assistant_ip:{client_ip}")
            if client_ip else 0
        )
    limit = settings.assistant_daily_limit
    if used > limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "daily assistant limit reached — it resets tomorrow",
        )
    if global_used > settings.assistant_daily_limit_global:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "the assistant has hit today's overall usage limit — it resets tomorrow",
        )
    if client_ip and ip_used > settings.assistant_daily_limit_per_ip:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "you've reached today's assistant limit from this connection — it resets tomorrow",
        )

    provider = "ServiceTitan"
    try:
        async with tenant_session(principal.tenant_id) as session:
            provider = display_name(await tenant_settings_repo.get_fsm_provider(session))
    except Exception:
        pass
    name, title = await _person_context(principal)

    system = build_system_prompt(
        provider=provider, user_name=name, user_title=title,
        role=principal.role, department=principal.department,
    )

    # INFERENCE ONLY — never training. This is the one live-LLM path in the running product; the
    # client is built with the documented inference-only / no-retention posture (the Anthropic
    # commercial API does not train on API traffic, and nothing here opts into any such program).
    # Figures still come from deterministic tools (ADR 0003); the model only narrates. Full lifecycle:
    # docs/AI_DATA_HANDLING.md.
    from app.assistant.llm_client import build_assistant_client

    client = build_assistant_client(settings)
    actions: list[dict] = []
    convo: list[dict] = list(messages)

    try:
        for _ in range(max(1, settings.assistant_max_tool_rounds)):
            response = await client.messages.create(
                model=settings.assistant_model,
                max_tokens=1200,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                tools=tools.TOOL_SPECS,
                messages=convo,
            )
            if response.stop_reason != "tool_use":
                reply = "\n".join(
                    b.text for b in response.content if getattr(b, "type", "") == "text"
                ).strip()
                return {
                    "reply": reply or "(no reply)",
                    "actions": actions,
                    "usage": {"used_today": used, "daily_limit": limit},
                }
            convo.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if getattr(block, "type", "") != "tool_use":
                    continue
                payload, summary = await _handle_tool(principal, block.name, dict(block.input or {}))
                if summary:
                    actions.append({"tool": block.name, "summary": summary})
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": payload}
                )
            convo.append({"role": "user", "content": results})
        # Tool-round budget exhausted — return what we have rather than looping forever.
        return {
            "reply": "I ran out of tool budget on that one — here's where I got to: "
                     + ("; ".join(a["summary"] for a in actions) or "no tools completed."),
            "actions": actions,
            "usage": {"used_today": used, "daily_limit": limit},
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "the assistant had trouble responding — try again"
        )
