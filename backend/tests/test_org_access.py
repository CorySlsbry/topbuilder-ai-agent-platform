"""Pure unit tests for per-person agent access + the manage authorization rule."""
from __future__ import annotations

import pytest

from app.org import access, permissions


def test_effective_agents_is_department_default_without_overrides() -> None:
    assert access.effective_agents("finance") == sorted(permissions.DEPT_AGENTS["finance"])


def test_grant_adds_an_agent_outside_the_department_default() -> None:
    # finance default has no 'workforce'; an explicit grant adds it.
    assert "workforce" not in permissions.DEPT_AGENTS["finance"]
    result = access.effective_agents("finance", {"workforce": "grant"})
    assert "workforce" in result
    assert set(result) == set(permissions.DEPT_AGENTS["finance"]) | {"workforce"}


def test_revoke_removes_an_agent_the_department_would_allow() -> None:
    assert "financial" in permissions.DEPT_AGENTS["finance"]
    result = access.effective_agents("finance", {"financial": "revoke"})
    assert "financial" not in result


def test_unknown_agent_or_department_is_ignored_not_crashed() -> None:
    assert access.effective_agents("does_not_exist") == []
    assert access.effective_agents("finance", {"made_up_agent": "grant"}) == sorted(
        permissions.DEPT_AGENTS["finance"]
    )


def test_leadership_sees_every_agent() -> None:
    assert access.effective_agents("leadership") == sorted(permissions.ALL_AGENTS)


def test_agent_states_flags_default_vs_override() -> None:
    states = {s["agent"]: s for s in access.agent_states("finance", {"workforce": "grant"})}
    # every agent is represented exactly once
    assert set(states) == set(permissions.ALL_AGENTS)
    assert states["financial"] == {"agent": "financial", "enabled": True, "default": True, "overridden": False}
    assert states["workforce"] == {"agent": "workforce", "enabled": True, "default": False, "overridden": True}
    assert states["routing"]["enabled"] is False


MANAGE_CASES = [
    # (desc, kwargs, expected)
    ("unrestricted manages anyone", dict(caller_unrestricted=True, caller_person_id=None, caller_role_tier=None, caller_department=None, person_manager_id="m"), True),
    ("direct manager", dict(caller_unrestricted=False, caller_person_id="boss", caller_role_tier="ic", caller_department="finance", person_manager_id="boss"), True),
    ("manager-tier same dept", dict(caller_unrestricted=False, caller_person_id="c", caller_role_tier="manager", caller_department="finance", person_manager_id="someoneelse"), True),
    ("exec same dept", dict(caller_unrestricted=False, caller_person_id="c", caller_role_tier="exec", caller_department="finance", person_manager_id=None), True),
    ("ic same dept cannot", dict(caller_unrestricted=False, caller_person_id="c", caller_role_tier="ic", caller_department="finance", person_manager_id="x"), False),
    ("manager different dept cannot", dict(caller_unrestricted=False, caller_person_id="c", caller_role_tier="manager", caller_department="field", person_manager_id="x"), False),
    ("no person link cannot", dict(caller_unrestricted=False, caller_person_id=None, caller_role_tier="manager", caller_department="finance", person_manager_id="x"), False),
]


@pytest.mark.parametrize("desc,kwargs,expected", MANAGE_CASES, ids=[c[0] for c in MANAGE_CASES])
def test_can_manage_person(desc: str, kwargs: dict, expected: bool) -> None:
    got = access.can_manage_person(person_id="target", person_department="finance", **kwargs)
    assert got is expected


def test_cannot_manage_self_even_as_manager() -> None:
    # A manager-tier caller who IS the target person cannot self-grant.
    assert (
        access.can_manage_person(
            caller_unrestricted=False,
            caller_person_id="self",
            caller_role_tier="manager",
            caller_department="finance",
            person_id="self",
            person_manager_id=None,
            person_department="finance",
        )
        is False
    )


@pytest.mark.parametrize(
    "event_type,expected",
    [
        ("Employee.Created", "hired"),
        ("Technician.Activated", "hired"),
        ("TeamMember.Onboarded", "hired"),
        ("Employee.Deactivated", "departed"),
        ("Technician.Terminated", "departed"),
        ("Employee.Deleted", "departed"),
        ("Job.Completed", None),
        ("Invoice.Created", None),  # 'create' but not an employee event
        ("unknown", None),
    ],
)
def test_classify_employee_event(event_type: str, expected: str | None) -> None:
    assert access.classify_employee_event(event_type) == expected


@pytest.mark.parametrize(
    "agent_key,mode,ok",
    [
        ("financial", "grant", True),
        ("workforce", "revoke", True),
        ("booking", "default", True),
        ("nope", "grant", False),
        ("financial", "sideways", False),
    ],
)
def test_validate_override(agent_key: str, mode: str, ok: bool) -> None:
    if ok:
        access.validate_override(agent_key, mode)
    else:
        with pytest.raises(ValueError):
            access.validate_override(agent_key, mode)
