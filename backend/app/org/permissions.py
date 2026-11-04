"""Department-scoped agent permissions — PURE (no DB, no IO).

The single source of truth mapping a membership's department to the agents it may use and the
frontend sections it may see. Enforcement is server-side (api/deps.require_agent_access); the UI
only mirrors these maps for wayfinding. Semantics: None = unrestricted (admin role, no department,
or leadership); an UNKNOWN department fails CLOSED (empty set — no agents, no sections).
"""
from __future__ import annotations

ALL_AGENTS: frozenset[str] = frozenset(
    {"workforce", "financial", "inventory", "booking", "routing", "documents", "collections",
     "pricebook"}
)

# Every customer-facing frontend section key (what "all sections" expands to).
# 'executive' and 'kpitrends' are deliberately in NO department's DEPT_SECTIONS list: leadership
# maps to None (= all sections), so only unrestricted principals ever see the executive KPI view
# and the KPI-trends view (both gate on /v1/org/scorecard* which 403s a department-scoped login).
ALL_SECTIONS: tuple[str, ...] = (
    "dispatch", "dispatchboard", "capacity", "frontdesk", "collections", "documents", "pricebook",
    "controls", "learning", "issues", "businessplan", "approvals",
    "workforce", "financial", "inventory", "booking", "organization", "executive", "kpitrends",
)

# department key -> the agents that department may use.
DEPT_AGENTS: dict[str, frozenset[str]] = {
    "leadership": ALL_AGENTS,
    "front_office": frozenset({"booking", "documents", "collections"}),
    "dispatch": frozenset({"routing"}),
    "field": frozenset({"workforce"}),
    "sales": frozenset({"booking"}),
    "finance": frozenset({"financial", "documents", "collections", "pricebook"}),
    "warehouse": frozenset({"inventory", "pricebook"}),
    # NOTE: the Ads-CRM 'ads' agent is intentionally ABSENT from ALL_AGENTS and every department here.
    # It is operator-only GTM tooling (ADR 0009), not a tenant agent: its /v1/crm + /v1/ads routes gate on
    # require_admin + the platform-operator allowlist, and the action gate's can_use_agent passes for
    # unrestricted operators (allowed_agents == None). Adding it to the tenant maps would wrongly surface
    # it in the tenant org overview.
}

# department key -> the frontend section keys that department may see (None = all sections).
# 'organization' is always included — block content, not wayfinding. Each new section is granted
# to the department that already owns its agent (so a grant is reachable in the nav, not stranded):
#   collections  -> finance + front_office (both have the collections agent)
#   capacity     -> field (Workforce agent — capacity is a Workforce view)
#   dispatchboard-> dispatch (Routing agent — the P1/P2/P3 triage board is Routing)
#   pricebook    -> finance + warehouse (both have the pricebook agent — it's materials cost x price)
# 'issues' / 'businessplan' are deliberately leadership-only (the EOS L10 surface) — in NO dept list,
# and their routes 403 for restricted principals.
# 'approvals' (the My-Approvals inbox) is granted to every department: the route + service filter the
# queue to each principal's own department, so a lead only ever sees and acts on their own actions.
DEPT_SECTIONS: dict[str, tuple[str, ...] | None] = {
    "leadership": None,
    "front_office": ("frontdesk", "booking", "documents", "collections", "approvals", "organization"),
    "dispatch": ("dispatch", "dispatchboard", "approvals", "organization"),
    "field": ("workforce", "capacity", "approvals", "organization"),
    "sales": ("booking", "approvals", "organization"),
    "finance": ("financial", "documents", "collections", "pricebook", "approvals", "organization"),
    "warehouse": ("inventory", "pricebook", "approvals", "organization"),
}

# The 7 demo departments (key/name/color/sort) — color drives ALL UI coding.
DEPARTMENTS: list[dict] = [
    {"key": "leadership", "name": "Leadership", "color": "#f59e0b", "sort": 1},
    {"key": "front_office", "name": "Front Office", "color": "#38bdf8", "sort": 2},
    {"key": "dispatch", "name": "Dispatch", "color": "#a78bfa", "sort": 3},
    {"key": "field", "name": "Field Operations", "color": "#34d399", "sort": 4},
    {"key": "sales", "name": "Sales", "color": "#fb7185", "sort": 5},
    {"key": "finance", "name": "Finance & Accounting", "color": "#818cf8", "sort": 6},
    {"key": "warehouse", "name": "Warehouse & Inventory", "color": "#fb923c", "sort": 7},
]

# The agent cards shown on the Organization Brain (key, label, owning departments, description).
AGENT_CARDS: list[dict] = [
    {
        "key": "workforce",
        "label": "Workforce Agent",
        "dept_keys": ["field", "leadership"],
        "description": "Forecasts understaffing and avoidable overtime across the field schedule.",
    },
    {
        "key": "financial",
        "label": "Financial Agent",
        "dept_keys": ["finance", "leadership"],
        "description": "Projects cash and surfaces margin leakage — deterministic numbers, narrated.",
    },
    {
        "key": "inventory",
        "label": "Inventory Agent",
        "dept_keys": ["warehouse"],
        "description": "Reorders, shrinkage, unbilled materials, and vendor savings.",
    },
    {
        "key": "booking",
        "label": "Booking Agent",
        "dept_keys": ["front_office", "sales"],
        "description": "Qualifies, slots, and values every inbound call 24/7.",
    },
    {
        "key": "routing",
        "label": "Routing Agent",
        "dept_keys": ["dispatch"],
        "description": "Drive-time-optimized daily assignment plan for dispatch.",
    },
    {
        "key": "documents",
        "label": "Documents Agent",
        "dept_keys": ["front_office", "finance"],
        "description": "Classifies, extracts, and files every document to the right place.",
    },
    {
        "key": "collections",
        "label": "Collections Agent",
        "dept_keys": ["finance", "front_office"],
        "description": "Works the A/R aging worklist 24/7 — drafts dunning email/SMS/calls, tracks promise-to-pay.",
    },
    {
        "key": "pricebook",
        "label": "Pricebook Agent",
        "dept_keys": ["finance", "warehouse"],
        "description": "Keeps materials costs current from vendor updates and re-prices every item under the sold-hour model.",
    },
]


def allowed_agents(role: str, department: str | None) -> frozenset[str] | None:
    """Agents this principal may use. None = unrestricted; unknown department fails CLOSED."""
    if role == "admin" or department is None or department == "leadership":
        return None
    return DEPT_AGENTS.get(department, frozenset())


def allowed_sections(role: str, department: str | None) -> tuple[str, ...] | None:
    """Frontend sections this principal may see. Same semantics as allowed_agents."""
    if role == "admin" or department is None:
        return None
    sections = DEPT_SECTIONS.get(department, ())
    return sections  # leadership maps to None (all sections); unknown -> () fails closed


def can_use_agent(role: str, department: str | None, agent: str) -> bool:
    allowed = allowed_agents(role, department)
    return allowed is None or agent in allowed
