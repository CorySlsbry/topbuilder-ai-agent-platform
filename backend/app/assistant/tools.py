"""The assistant's tool registry — a CLOSED set of capabilities, permission-checked server-side.

Pure module (no DB/IO): tool specs, the permission gate, input validation, and history hygiene live
here so they are unit-testable; the async handlers that touch the database live in `service.py`.
Permissions piggyback on the org layer (`app.org.permissions`): department-scoped sign-ins can only
read the agents their department includes, and workflow changes require the operator (admin) role —
the same bar as every other write surface (ADR 0007).
"""
from __future__ import annotations

from typing import Any

from app.org import permissions

# Agents the assistant can read results for. The 6 org-mapped agents plus the two operator-layer
# agents (email, seo) — the org permission map naturally blocks email/seo for department-scoped
# sign-ins because they appear in no department's allow-list.
ASSISTANT_AGENTS = (
    "workforce", "financial", "inventory", "booking", "routing", "documents", "email", "seo",
)

ADMIN_TOOLS = frozenset({"update_email_workflow"})
# Tool surfaces that mirror operator-only routes (routes_email/routes_seo require require_admin):
# the assistant must hold the SAME bar or it becomes a permission bypass.
OPERATOR_AGENTS = frozenset({"email", "seo"})
OPERATOR_READ_TOOLS = frozenset({"list_email_workflows"})
# Writes mirror the runner bar (deps.RUNNER_ROLES): read-only viewers can't create tasks via chat.
WRITE_ROLES = frozenset({"admin", "analyst"})

TOOL_SPECS: list[dict] = [
    {
        "name": "get_agent_results",
        "description": (
            "Fetch the latest persisted results of one of the company's AI agents (deterministic "
            "figures — quote them verbatim). Returns null if the agent hasn't run yet."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"agent": {"type": "string", "enum": list(ASSISTANT_AGENTS)}},
            "required": ["agent"],
        },
    },
    {
        "name": "list_communications",
        "description": "Recent inbound communications across all channels (calls, sms, email, web).",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 25}},
        },
    },
    {
        "name": "list_tasks",
        "description": "The office task worklist. Optionally filter by status (open|in_progress|done).",
        "input_schema": {
            "type": "object",
            "properties": {"status": {"type": "string", "enum": ["open", "in_progress", "done"]}},
        },
    },
    {
        "name": "create_task",
        "description": "Create a task on the office worklist (administrative work the user asks for).",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "detail": {"type": "string"},
                "department": {"type": "string", "enum": sorted(permissions.DEPT_AGENTS)},
                "priority": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["title", "department"],
        },
    },
    {
        "name": "list_email_workflows",
        "description": (
            "The company's automated outbound email workflows with send/open/reply performance vs "
            "benchmark, any proposed rewrite for underperformers, and any rewrite already applied."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "update_email_workflow",
        "description": (
            "OPERATOR ONLY — apply new copy (subject + preview line) to an outbound email workflow. "
            "Use only when the user explicitly asks to change/fix/apply a rewrite. This changes real "
            "outbound email and is audited."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "subject": {"type": "string"},
                "preview": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["workflow_id", "subject", "preview"],
        },
    },
]


def can_call(role: str, department: str | None, tool: str, *, agent: str | None = None) -> tuple[bool, str]:
    """The permission gate every tool call passes through. Fail closed: unknown tool -> refused.
    Mirrors the REST bars exactly: operator-only surfaces stay operator-only, writes stay
    runner-only — the assistant is a convenience, never a permission bypass."""
    if tool not in {t["name"] for t in TOOL_SPECS}:
        return False, f"unknown tool '{tool}'"
    if tool in ADMIN_TOOLS and role != "admin":
        return False, "changing email workflows needs an operator (admin) sign-in"
    if tool in OPERATOR_READ_TOOLS and role != "admin":
        return False, "email workflows are an operator surface — this needs an admin sign-in"
    if tool == "create_task" and role not in WRITE_ROLES:
        return False, "creating tasks needs an analyst or operator sign-in"
    if tool == "get_agent_results":
        if agent not in ASSISTANT_AGENTS:
            return False, f"unknown agent '{agent}'"
        if agent in OPERATOR_AGENTS and role != "admin":
            return False, f"the {agent} agent is an operator surface — this needs an admin sign-in"
        if not permissions.can_use_agent(role, department, agent):
            return False, f"your department scope does not include the {agent} agent"
    return True, ""


def needs_operator_2fa(tool: str, *, agent: str | None = None) -> bool:
    """Tools mirroring require_admin surfaces also require the verified second factor (aal2)."""
    return (
        tool in ADMIN_TOOLS
        or tool in OPERATOR_READ_TOOLS
        or (tool == "get_agent_results" and agent in OPERATOR_AGENTS)
    )


def validate_override(args: dict) -> tuple[dict | None, str | None]:
    """Validate update_email_workflow input -> (clean, None) or (None, reason)."""
    workflow_id = str(args.get("workflow_id", "")).strip()
    subject = str(args.get("subject", "")).strip()
    preview = str(args.get("preview", "")).strip()
    rationale = str(args.get("rationale", "")).strip()
    if not (1 <= len(workflow_id) <= 64):
        return None, "workflow_id must be 1-64 characters"
    if not (3 <= len(subject) <= 120):
        return None, "subject must be 3-120 characters"
    if not (3 <= len(preview) <= 200):
        return None, "preview must be 3-200 characters"
    if len(rationale) > 500:
        return None, "rationale must be at most 500 characters"
    return {
        "workflow_id": workflow_id, "subject": subject,
        "preview": preview, "rationale": rationale,
    }, None


def validate_task(args: dict) -> tuple[dict | None, str | None]:
    """Validate create_task input -> (clean, None) or (None, reason)."""
    title = str(args.get("title", "")).strip()
    detail = str(args.get("detail", "")).strip() or None
    department = str(args.get("department", "")).strip()
    priority = args.get("priority", 5)
    if not (3 <= len(title) <= 200):
        return None, "title must be 3-200 characters"
    if department not in permissions.DEPT_AGENTS:
        return None, f"unknown department '{department}'"
    if not isinstance(priority, int) or not (1 <= priority <= 10):
        return None, "priority must be an integer 1-10"
    if detail and len(detail) > 1000:
        detail = detail[:1000]
    return {"title": title, "detail": detail, "department": department, "priority": priority}, None


def sanitize_history(
    messages: list[dict], *, max_messages: int = 12, max_chars: int = 4000
) -> list[dict[str, Any]]:
    """Client history -> a safe Anthropic message list: known roles only, clipped content, last N
    turns, and it must start with a user turn (drop leading assistant messages)."""
    clean: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        clean.append({"role": role, "content": content[:max_chars]})
    clean = clean[-max_messages:]
    while clean and clean[0]["role"] != "user":
        clean.pop(0)
    while clean and clean[-1]["role"] != "user":  # a trailing assistant turn would be a prefill
        clean.pop()
    return clean


def clip(value: str, limit: int = 6000) -> str:
    return value if len(value) <= limit else value[:limit] + " …[truncated]"
