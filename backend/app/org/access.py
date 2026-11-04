"""Per-person AI-agent access — PURE (no DB, no IO).

Extends the department-scoped permission maps (app/org/permissions.py) with per-individual
grant/revoke overrides that a manager or director can set on the org sphere, plus the authorization
rule for WHO may set them. Enforcement is server-side (api/routes_org); this module is the math.
"""
from __future__ import annotations

from app.org import permissions

# role_tiers that may manage another person's access within their own department.
MANAGER_TIERS: frozenset[str] = frozenset({"owner", "exec", "manager"})


def effective_agents(department_key: str, overrides: dict[str, str] | None = None) -> list[str]:
    """The agents a person may actually use: their department default, then per-person overrides.

    overrides maps agent_key -> 'grant' | 'revoke'. 'grant' adds an agent the department wouldn't
    include; 'revoke' removes one it would. Unknown agent keys are ignored. Always returns a sorted,
    concrete list (a person's effective access is never "unrestricted/None" — it's an explicit set).
    """
    agents = set(permissions.DEPT_AGENTS.get(department_key, frozenset()))
    for agent, mode in (overrides or {}).items():
        if agent not in permissions.ALL_AGENTS:
            continue
        if mode == "grant":
            agents.add(agent)
        elif mode == "revoke":
            agents.discard(agent)
    return sorted(agents)


def agent_states(department_key: str, overrides: dict[str, str] | None = None) -> list[dict]:
    """Per-agent UI state for every agent: whether it's on, and whether that's the department
    default or an explicit override. Powers the grant/revoke toggles in the profile panel."""
    overrides = overrides or {}
    default = set(permissions.DEPT_AGENTS.get(department_key, frozenset()))
    effective = set(effective_agents(department_key, overrides))
    states: list[dict] = []
    for agent in sorted(permissions.ALL_AGENTS):
        on = agent in effective
        by_default = agent in default
        states.append(
            {
                "agent": agent,
                "enabled": on,
                "default": by_default,
                "overridden": agent in overrides and on != by_default,
            }
        )
    return states


def can_manage_person(
    *,
    caller_unrestricted: bool,
    caller_person_id: str | None,
    caller_role_tier: str | None,
    caller_department: str | None,
    person_id: str,
    person_manager_id: str | None,
    person_department: str,
) -> bool:
    """May the caller grant/revoke this person's agent access?

    True when the caller is unrestricted (admin / leadership / platform operator), is the person's
    direct manager, or is a manager-tier in the same department. A person can never manage their own
    access (a self-grant would defeat the control), and nobody department-scoped reaches across
    departments.
    """
    if caller_unrestricted:
        return True
    if caller_person_id is None or caller_person_id == person_id:
        return False
    if person_manager_id is not None and caller_person_id == person_manager_id:
        return True
    return caller_role_tier in MANAGER_TIERS and caller_department == person_department


def classify_employee_event(event_type: str) -> str | None:
    """Map a provider webhook event type to a roster action so the org auto-updates in real time.

    Returns 'hired' for employee/technician create/activate, 'departed' for deactivate/terminate/
    delete, and None for anything else (no roster change). Matches loosely because providers name
    these events differently (Employee.Created, Technician.Deactivated, TeamMember.Terminated, ...).
    """
    e = event_type.lower()
    if not any(k in e for k in ("employee", "technician", "teammember", "team_member", "user")):
        return None
    if any(k in e for k in ("deactiv", "terminat", "delet", "fired", "offboard", "remove", "inactive")):
        return "departed"
    if any(k in e for k in ("creat", "hire", "activ", "add", "onboard")):
        return "hired"
    return None


def validate_override(agent_key: str, mode: str) -> None:
    """Raise ValueError on an unknown agent or mode — the endpoint turns this into a 400/422."""
    if agent_key not in permissions.ALL_AGENTS:
        raise ValueError(f"unknown agent '{agent_key}'")
    if mode not in ("grant", "revoke", "default"):
        raise ValueError(f"mode must be grant|revoke|default, got '{mode}'")
