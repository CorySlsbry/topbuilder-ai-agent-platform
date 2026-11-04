"""Organization Brain endpoints — the seeded org model (company → departments → people → agents)
plus what the calling principal may access. Permission maps live in app/org/permissions.py."""
from __future__ import annotations

import importlib
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import get_principal, require_admin
from app.db import tenant_session
from app.org import access, eos, forecast, issue_store, kpis, permissions
from app.org import eos_data as eos_source
from app.org import scorecard as scorecard_engine
from app.org import scorecard_data as scorecard_source
from app.org.seed import SEED_TENANTS
from app.repositories import demo_runs as demo_runs_repo
from app.repositories import org as org_repo
from app.repositories import runs as runs_repo
from app.security import Principal

router = APIRouter(prefix="/v1/org", tags=["org"])


@router.get("/overview")
async def overview(principal: Principal = Depends(get_principal)) -> dict:
    """The whole org in one read: company, departments (+head counts), people, agent cards, and
    the caller's own access scope. Seeds the demo roster on first read (idempotent)."""
    await org_repo.ensure_seeded(principal.tenant_id)
    result = await org_repo.get_overview(principal.tenant_id)
    agents = permissions.allowed_agents(principal.role, principal.department)
    result["caller_access"] = {
        "department": principal.department,
        "allowed_agents": sorted(agents) if agents is not None else None,
    }
    return result


@router.get("/kpis")
async def executive_kpis(principal: Principal = Depends(get_principal)) -> dict:
    """Enterprise KPI rollup from each agent's latest persisted run — the executive view.

    Restricted server-side to unrestricted principals (admin, no-department, leadership);
    department-scoped logins get a 403, mirroring the per-agent gates. Figures are ONLY summed
    and relabeled from persisted deterministic run results (ADR 0003)."""
    if permissions.allowed_agents(principal.role, principal.department) is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"department '{principal.department}' does not include the executive view",
        )
    latest: dict[str, dict | None] = {}
    for agent in sorted(permissions.ALL_AGENTS):
        # Lazy per-agent import + best-effort read: one agent failing never breaks the dashboard.
        try:
            service = importlib.import_module(f"app.agents.{agent}.service")
            latest[agent] = await service.get_latest_result(principal)
        except Exception:
            latest[agent] = None
    await org_repo.ensure_seeded(principal.tenant_id)
    overview = await org_repo.get_overview(principal.tenant_id)
    return kpis.aggregate_kpis(
        latest,
        departments=overview["departments"],
        employee_count=overview["company"]["employee_count"],
    )


_MAX_TIMESERIES_DAYS = 366  # cap the window so the date axis stays bounded.


@router.get("/kpis/timeseries")
async def executive_kpis_timeseries(
    principal: Principal = Depends(get_principal),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    granularity: str = Query(default="day"),
    departments: str | None = Query(default=None),
) -> dict:
    """Daily KPI history across the agents — the executive "go backwards" view (trends + insight,
    not just today's red/green). Same auth bar as /v1/org/kpis (unrestricted principals only).

    Reads the persisted succeeded runs over [start, end] (RLS-scoped to the caller's tenant) and
    hands them to the PURE `aggregate_kpis_timeseries`, which only summarizes the figures the agents
    already computed deterministically and persisted (ADR 0003 — never recomputes a business
    number). `departments` is an optional comma-separated key filter; `granularity` is accepted for
    forward-compatibility (the pure layer is daily today)."""
    if permissions.allowed_agents(principal.role, principal.department) is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"department '{principal.department}' does not include the executive view",
        )
    end = end or date.today()
    start = start or (end - timedelta(days=29))
    if start > end:
        start, end = end, start
    start = max(start, end - timedelta(days=_MAX_TIMESERIES_DAYS))
    dept_filter = (
        [d.strip() for d in departments.split(",") if d.strip()] if departments else None
    )

    # Demo-only seed-on-read (mirrors org_repo.ensure_seeded below): a sparse window on a DEMO
    # tenant is backfilled with deterministic fixture history first, so the executive charts show a
    # realistic daily story instead of two dots. Non-demo tenants are never touched; a seeding
    # failure never breaks the read (best-effort inside the helper).
    await demo_runs_repo.ensure_demo_run_history(principal.tenant_id, start=start, end=end)

    async with tenant_session(principal.tenant_id) as session:
        runs = await runs_repo.list_succeeded_runs_in_range(session, start=start, end=end)

    await org_repo.ensure_seeded(principal.tenant_id)
    overview = await org_repo.get_overview(principal.tenant_id)
    return kpis.aggregate_kpis_timeseries(
        runs, overview["departments"], start, end, dept_filter
    )


_MAX_SCORECARD_WEEKS = 52  # window cap: up to a rolling year of weekly columns.
_MAX_FORECAST_WEEKS = 52   # forward projection cap (13 = a CFO quarter, 26 = six months).


@router.get("/scorecard")
async def department_scorecard(
    principal: Principal = Depends(get_principal),
    weeks: int = Query(default=13),
    departments: str | None = Query(default=None),
) -> dict:
    """The auto-computed Department Scorecard — the Bloom Growth L10 replacement.

    Same auth bar as /v1/org/kpis: unrestricted principals (admin / no-department / leadership)
    only; a department-scoped login gets a 403. Every figure is produced by the PURE, deterministic
    ``compute_scorecard`` engine (ADR 0003 — the LLM never computes one); money is emitted in
    dollars. Returns the full ``Scorecard`` (departments → kpis[+series] + per-entity rows, plus the
    complete ``catalog`` so the frontend selector knows every KPI).

    ``weeks`` (1..26) trims to the most recent N weekly columns. ``departments`` is an optional
    comma-separated key filter over the four scorecard departments
    (sales · operations · sales_marketing · finance)."""
    if permissions.allowed_agents(principal.role, principal.department) is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"department '{principal.department}' does not include the executive view",
        )
    if weeks < 1 or weeks > _MAX_SCORECARD_WEEKS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"weeks must be between 1 and {_MAX_SCORECARD_WEEKS}",
        )
    wanted = (
        {d.strip() for d in departments.split(",") if d.strip()} if departments else None
    )

    # RLS-scoped session for parity with /v1/org/kpis and forward-compat with a live per-tenant
    # source; the fixture source is the working data path today (SERVICETITAN_MODE=fixture).
    async with tenant_session(principal.tenant_id):
        data = scorecard_source.get_scorecard_data()
    card = scorecard_engine.compute_scorecard(data, weeks=weeks)
    payload = scorecard_engine.scorecard_to_json(card)
    if wanted is not None:
        payload["departments"] = [d for d in payload["departments"] if d["key"] in wanted]
    return payload


def _series_json(series) -> list[dict]:
    return [{"date": p.date, "value": p.value, "projected": p.projected} for p in series]


@router.get("/scorecard/trends")
async def scorecard_trends(
    principal: Principal = Depends(get_principal),
    weeks: int = Query(default=52, description="rolling-year history window (1..52 weekly columns)"),
    forecast_weeks: int = Query(default=26, description="forward projection horizon (0..52; 13=quarter, 26=six months)"),
    departments: str | None = Query(default=None),
    kpis: str | None = Query(default=None, description="optional comma-separated KPI keys to limit the payload"),
) -> dict:
    """Premium trend view: per KPI, the rolling-year WEEKLY actuals + a deterministic forward BAND
    (13-week and 6-month projections, flagged ``projected``) + a MONTHLY rollup — so seasonality is
    visible (last year behind, the seasonal projection ahead). Same unrestricted (leadership/operator)
    read bar as /scorecard. Every point is deterministic (ADR 0003): the forecast is a damped trend
    plus a year-over-year seasonal overlay when a full cycle of history exists, never an LLM guess."""
    if permissions.allowed_agents(principal.role, principal.department) is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"department '{principal.department}' does not include the executive view",
        )
    if weeks < 1 or weeks > _MAX_SCORECARD_WEEKS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"weeks must be between 1 and {_MAX_SCORECARD_WEEKS}")
    if forecast_weeks < 0 or forecast_weeks > _MAX_FORECAST_WEEKS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"forecast_weeks must be between 0 and {_MAX_FORECAST_WEEKS}")
    wanted_depts = {d.strip() for d in departments.split(",") if d.strip()} if departments else None
    wanted_kpis = {k.strip() for k in kpis.split(",") if k.strip()} if kpis else None

    async with tenant_session(principal.tenant_id):
        data = scorecard_source.get_scorecard_data()
    card = scorecard_engine.compute_scorecard(data, weeks=weeks)

    out_depts: list[dict] = []
    for dep in card.departments:
        if wanted_depts is not None and dep.key not in wanted_depts:
            continue
        kpi_rows: list[dict] = []
        for kv in dep.kpis:
            if wanted_kpis is not None and kv.key not in wanted_kpis:
                continue
            kdef = scorecard_engine.CATALOG_BY_KEY[kv.key]
            actuals = kv.series  # rolling-year weekly actuals (projected=False)
            # Booleans (a flag) aren't projected; everything else gets the forward band.
            fwd = [] if kdef.unit == "bool" else forecast.project_series(actuals, forecast_weeks)
            weekly = list(actuals) + fwd
            monthly = forecast.to_monthly(weekly, forecast.aggregation_for(kv.key, kdef.unit))
            kpi_rows.append({
                "key": kv.key, "label": kdef.label, "unit": kdef.unit,
                "calculated": kdef.calculated, "goal": kdef.goal,
                "higher_is_better": kdef.higher_is_better, "description": kdef.description,
                "current": kv.value, "on_goal": kv.on_goal, "delta_pct": kv.delta_pct,
                "weekly": _series_json(weekly), "monthly": _series_json(monthly),
                "forecast_from": fwd[0].date if fwd else None,
            })
        out_depts.append({"key": dep.key, "label": dep.label, "source": dep.source, "kpis": kpi_rows})

    return {
        "history_weeks": weeks,
        "forecast_weeks": forecast_weeks,
        "departments": out_depts,
        "catalog": [scorecard_engine.kpi_def_json(d) for d in scorecard_engine.CATALOG],
    }


# --------------------------------------------------------------------------------------------
# EOS communication hub — Issues (L10 IDS list) + Business Plan (budget-to-actual + trailing-12).
# The sticky Bloom Growth value BEYOND the scorecard; framed with the org chart + tasks as the hub.
# Same unrestricted (leadership/operator) READ bar as /v1/org/kpis + /v1/org/scorecard.
# --------------------------------------------------------------------------------------------


@router.get("/issues")
async def list_issues(principal: Principal = Depends(get_principal)) -> dict:
    """The L10 Issues list (IDS) — open + recently closed issues, owned + prioritized, with header
    counts. Unrestricted principals only (a department-scoped login gets a 403, mirroring the
    executive/scorecard views). Pure: the store starts from the seed and applies create/resolve."""
    _require_unrestricted(principal, "the issues list")
    issues = issue_store.list_issues(principal.tenant_id)
    return eos.issues_to_json(issues)


class IssueCreateIn(BaseModel):
    title: str
    owner: str | None = None
    department: str | None = None
    priority: int = 2  # 1 (highest) .. 3 (lowest)


@router.post("/issues", status_code=status.HTTP_201_CREATED)
async def create_issue(
    body: IssueCreateIn, principal: Principal = Depends(require_admin)
) -> dict:
    """Add an issue to the L10 list. A gated write (admin + AAL2, the action-gate bar — ADR 0007):
    the issue store is OUR data, not a ServiceTitan/QBO write, so it's a simple gated write rather
    than the propose→approve→execute path. Audited."""
    try:
        issue = issue_store.create_issue(
            principal.tenant_id,
            title=body.title,
            owner=body.owner or "Unassigned",
            department=body.department or "",
            priority=body.priority,
            created=date.today().isoformat(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    async with tenant_session(principal.tenant_id) as session:
        await runs_repo.insert_audit(
            session, actor=str(principal.user_id), action="org.issue.create",
            target=issue.id, detail={"title": issue.title, "priority": issue.priority},
        )
    return eos.issue_to_json(issue)


@router.post("/issues/{issue_id}/resolve")
async def resolve_issue(
    issue_id: str, principal: Principal = Depends(require_admin)
) -> dict:
    """Close an open issue (idempotent). Gated write (admin + AAL2); audited."""
    issue = issue_store.resolve_issue(
        principal.tenant_id, issue_id, resolved_on=date.today().isoformat()
    )
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="issue not found")
    async with tenant_session(principal.tenant_id) as session:
        await runs_repo.insert_audit(
            session, actor=str(principal.user_id), action="org.issue.resolve",
            target=issue.id, detail={"status": issue.status},
        )
    return eos.issue_to_json(issue)


@router.get("/business-plan")
async def business_plan(principal: Principal = Depends(get_principal)) -> dict:
    """The Business Plan — annual goals + this period's budget-to-actual + a trailing-12 P&L trend.

    Unrestricted principals only (same bar as the scorecard). Every figure comes from the PURE,
    deterministic ``eos`` engine (ADR 0003 — net income is derived from the lines, never stored);
    money is emitted in dollars. Live mode sources the P&L from QuickBooks (docs/QBO_DATA_MAP §3.2)
    and fails closed until the mapping is verified."""
    _require_unrestricted(principal, "the business plan")
    # RLS-scoped session for parity with /v1/org/scorecard + forward-compat with a live QBO source.
    async with tenant_session(principal.tenant_id):
        plan = eos_source.get_business_plan()
    return eos.business_plan_to_json(plan)


def _require_unrestricted(principal: Principal, view: str) -> None:
    """The leadership/operator gate shared by the EOS reads — a department-scoped login gets a 403."""
    if permissions.allowed_agents(principal.role, principal.department) is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"department '{principal.department}' does not include {view}",
        )


@router.get("/access-matrix")
async def access_matrix(principal: Principal = Depends(get_principal)) -> dict:
    """The full department → agents/sections truth table, straight from the permission maps.

    Any authenticated principal may read it — it powers wayfinding (e.g. view-as), while the
    per-agent dependencies remain the enforcement."""
    return {
        "departments": [
            {"key": d["key"], "name": d["name"], "color": d["color"], "sort": d["sort"]}
            for d in permissions.DEPARTMENTS
        ],
        "dept_agents": {k: sorted(v) for k, v in permissions.DEPT_AGENTS.items()},
        "dept_sections": {
            k: (list(v) if v is not None else None) for k, v in permissions.DEPT_SECTIONS.items()
        },
        "agents": permissions.AGENT_CARDS,
        "all_sections": list(permissions.ALL_SECTIONS),
    }


@router.get("/people/{person_id}")
async def person_profile(
    person_id: uuid.UUID, principal: Principal = Depends(get_principal)
) -> dict:
    """One person: profile, manager, direct reports, and the AI access their department grants.

    Org-chart fields (name/title/department/reports) are visible to anyone in the tenant, but the
    sensitive per-person fields — `ai_context` (behavioral instructions written for the AI) and
    `email` — are redacted for department-scoped logins, mirroring the executive-view gate. Only
    unrestricted principals (leadership / operator) see them."""
    result = await org_repo.get_person(principal.tenant_id, person_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="person not found")
    is_unrestricted = permissions.allowed_agents(principal.role, principal.department) is None
    if not is_unrestricted:
        result["person"].pop("ai_context", None)
        result["person"].pop("email", None)
    dept_key = result["person"]["department_key"]
    overrides = await org_repo.get_person_overrides(principal.tenant_id, person_id)
    effective = access.effective_agents(dept_key, overrides)
    sections = permissions.DEPT_SECTIONS.get(dept_key, ())
    caller = await org_repo.get_caller_person(principal.tenant_id, principal.person_id)
    can_manage = access.can_manage_person(
        caller_unrestricted=is_unrestricted,
        caller_person_id=principal.person_id,
        caller_role_tier=caller["role_tier"] if caller else None,
        caller_department=principal.department,
        person_id=str(person_id),
        person_manager_id=result["manager"]["id"] if result["manager"] else None,
        person_department=dept_key,
    )
    result["ai_access"] = {
        "agents": effective,
        "sections": list(sections) if sections is not None else list(permissions.ALL_SECTIONS),
        "not_accessible": sorted(set(permissions.ALL_AGENTS) - set(effective)),
        "agent_states": access.agent_states(dept_key, overrides),
        "can_manage": can_manage,
    }
    return result


class AgentOverrideIn(BaseModel):
    agent_key: str
    mode: str  # grant | revoke | default


@router.put("/people/{person_id}/agents")
async def set_person_agent(
    person_id: uuid.UUID,
    body: AgentOverrideIn,
    principal: Principal = Depends(get_principal),
) -> dict:
    """Grant or revoke one AI agent for an individual (mode='default' resets to the department
    default). Authorized server-side: only the person's manager, a manager-tier in their department,
    or an unrestricted operator/leadership may edit — never the person themselves. Audited (set_by)."""
    try:
        access.validate_override(body.agent_key, body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    person = await org_repo.get_person_min(principal.tenant_id, person_id)
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="person not found")
    is_unrestricted = permissions.allowed_agents(principal.role, principal.department) is None
    caller = await org_repo.get_caller_person(principal.tenant_id, principal.person_id)
    if not access.can_manage_person(
        caller_unrestricted=is_unrestricted,
        caller_person_id=principal.person_id,
        caller_role_tier=caller["role_tier"] if caller else None,
        caller_department=principal.department,
        person_id=str(person_id),
        person_manager_id=person["manager_id"],
        person_department=person["department_key"],
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only this person's manager, a director in their department, or an operator may change their access",
        )
    set_by = principal.email or str(principal.user_id)  # always-present actor id for the grant/revoke audit
    await org_repo.set_person_override(principal.tenant_id, person_id, body.agent_key, body.mode, set_by)
    overrides = await org_repo.get_person_overrides(principal.tenant_id, person_id)
    return {
        "agents": access.effective_agents(person["department_key"], overrides),
        "agent_states": access.agent_states(person["department_key"], overrides),
    }


def _fixture_roster(tenant_id: uuid.UUID) -> list[dict]:
    """Roster source while a tenant runs in demo/fixture mode — derived from the seed so a sync is a
    faithful, idempotent reconcile. At go-live the live provider adapter (ServiceTitan/HR employee
    roster) swaps in here, and a hire/fire webhook keeps it real-time."""
    spec = SEED_TENANTS.get(str(tenant_id))
    if spec is None:
        return []
    return [
        {
            "external_ref": p["slug"],
            "full_name": p["full_name"],
            "title": p["title"],
            "department_key": p["department"],
            "role_tier": p["role_tier"],
        }
        for p in spec["people"]
    ]


@router.post("/sync")
async def sync_roster(principal: Principal = Depends(get_principal)) -> dict:
    """Reconcile the org against the connected provider's employee roster — new hires appear on the
    sphere, departed people drop off — so the organization stays current automatically. Operator /
    leadership only; idempotent (re-running with the same roster is a no-op)."""
    if permissions.allowed_agents(principal.role, principal.department) is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="roster sync is operator-only")
    await org_repo.ensure_seeded(principal.tenant_id)
    return await org_repo.reconcile_roster(principal.tenant_id, _fixture_roster(principal.tenant_id))
