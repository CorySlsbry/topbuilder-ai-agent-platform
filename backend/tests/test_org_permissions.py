"""Oracle tests for the department permission maps + the seeded Canyon Ridge roster (PURE, no DB).

The truth tables here are the binding contract for the Alex demo: what each department may use,
the fail-closed semantics for unknown departments, and the integrity of the 38-person roster the
Organization Brain seeds on first read.
"""
from __future__ import annotations

import uuid

import pytest

from app.org import permissions, seed
from app.org.permissions import (
    ALL_AGENTS,
    ALL_SECTIONS,
    DEPT_AGENTS,
    DEPT_SECTIONS,
    allowed_agents,
    allowed_sections,
    can_use_agent,
)

EXPECTED_DEPT_AGENTS = {
    "leadership": {"workforce", "financial", "inventory", "booking", "routing", "documents", "collections", "pricebook"},
    "front_office": {"booking", "documents", "collections"},
    "dispatch": {"routing"},
    "field": {"workforce"},
    "sales": {"booking"},
    "finance": {"financial", "documents", "collections", "pricebook"},
    "warehouse": {"inventory", "pricebook"},
}

EXPECTED_HEADCOUNTS = {
    "leadership": 3,
    "front_office": 5,
    "dispatch": 3,
    "field": 18,
    "sales": 3,
    "finance": 3,
    "warehouse": 3,
}


# --- permission truth tables --------------------------------------------------------------------
def test_dept_agents_exact_truth_table():
    assert {k: set(v) for k, v in DEPT_AGENTS.items()} == EXPECTED_DEPT_AGENTS


def test_admin_role_is_unrestricted_even_with_a_department():
    assert allowed_agents("admin", "dispatch") is None


def test_no_department_means_unrestricted():
    assert allowed_agents("analyst", None) is None


def test_leadership_department_is_unrestricted():
    assert allowed_agents("analyst", "leadership") is None
    assert allowed_sections("analyst", "leadership") is None


def test_dispatch_analyst_gets_exactly_routing():
    assert allowed_agents("analyst", "dispatch") == frozenset({"routing"})


def test_unknown_department_fails_closed():
    assert allowed_agents("analyst", "skunkworks") == frozenset()
    assert allowed_sections("analyst", "skunkworks") == ()
    assert can_use_agent("analyst", "skunkworks", "booking") is False


@pytest.mark.parametrize("department,agents", sorted(EXPECTED_DEPT_AGENTS.items()))
def test_can_use_agent_matches_the_map(department: str, agents: set[str]):
    for agent in sorted(ALL_AGENTS):
        assert can_use_agent("analyst", department, agent) is (agent in agents)


def test_every_restricted_section_list_includes_organization():
    """Block content, not wayfinding — every department keeps the Organization Brain."""
    restricted = {k: v for k, v in DEPT_SECTIONS.items() if v is not None}
    assert restricted  # the rule is vacuous if nothing is restricted
    for sections in restricted.values():
        assert "organization" in sections


def test_executive_section_is_unrestricted_principals_only():
    """'executive' is a real section but in NO department list — leadership maps to None
    (all sections), so only unrestricted principals ever see the executive KPI view."""
    assert "executive" in ALL_SECTIONS
    for sections in DEPT_SECTIONS.values():
        if sections is not None:
            assert "executive" not in sections


def test_kpis_and_access_matrix_routes_are_registered_on_the_org_router():
    from app.api import routes_org

    paths = {route.path for route in routes_org.router.routes}
    assert {"/v1/org/kpis", "/v1/org/access-matrix"} <= paths


# --- seed roster integrity ------------------------------------------------------------------------
def test_roster_has_exactly_38_people_and_7_departments():
    assert len(seed.PEOPLE) == 38
    assert len(permissions.DEPARTMENTS) == 7


def test_headcounts_per_department():
    counts: dict[str, int] = {}
    for p in seed.PEOPLE:
        counts[p["department"]] = counts.get(p["department"], 0) + 1
    assert counts == EXPECTED_HEADCOUNTS


def test_every_manager_slug_resolves_to_a_roster_slug():
    slugs = {p["slug"] for p in seed.PEOPLE}
    assert len(slugs) == len(seed.PEOPLE)  # slugs are unique
    for p in seed.PEOPLE:
        if p["manager_slug"] is not None:
            assert p["manager_slug"] in slugs, p["slug"]


def test_manager_edges_terminate_at_the_owner_no_cycles():
    by_slug = {p["slug"]: p for p in seed.PEOPLE}
    for p in seed.PEOPLE:
        seen: set[str] = set()
        cursor = p
        while cursor["manager_slug"] is not None:
            assert cursor["slug"] not in seen, f"manager cycle through {cursor['slug']}"
            seen.add(cursor["slug"])
            cursor = by_slug[cursor["manager_slug"]]
        assert cursor["slug"] == "alex"


def test_alex_is_the_only_owner_and_has_no_manager():
    owners = [p for p in seed.PEOPLE if p["role_tier"] == "owner"]
    assert [p["slug"] for p in owners] == ["alex"]
    assert owners[0]["manager_slug"] is None
    assert owners[0]["full_name"] == "Alex"
    assert owners[0]["title"] == "Owner / CEO"


def test_alex_person_id_matches_the_pinned_uuid():
    """The deterministic uuid5 both sides (and the live memberships row) link against."""
    assert seed.person_id("alex") == uuid.UUID("5f999a9e-dbe1-531b-a4a4-90454df7ff5d")


def test_department_colors_are_unique():
    colors = [d["color"] for d in permissions.DEPARTMENTS]
    assert len(set(colors)) == len(colors)


def test_every_person_has_a_nonempty_ai_context():
    for p in seed.PEOPLE:
        assert p["ai_context"].strip(), p["slug"]


def test_deterministic_ids_are_stable():
    for p in seed.PEOPLE:
        assert seed.person_id(p["slug"]) == seed.person_id(p["slug"])
    for d in permissions.DEPARTMENTS:
        assert seed.dept_id(d["key"]) == seed.dept_id(d["key"])
    person_ids = {seed.person_id(p["slug"]) for p in seed.PEOPLE}
    assert len(person_ids) == len(seed.PEOPLE)  # no id collisions


def test_seed_tenants_carries_only_canyonridge():
    assert list(seed.SEED_TENANTS) == [seed.CANYONRIDGE_TENANT_ID]
    spec = seed.SEED_TENANTS[seed.CANYONRIDGE_TENANT_ID]
    assert spec["company_name"] == "Canyon Ridge Mechanical"
    assert spec["provider"] == "servicetitan"
    assert len(spec["people"]) == 38
