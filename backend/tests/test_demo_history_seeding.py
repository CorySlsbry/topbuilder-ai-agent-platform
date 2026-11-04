"""Gating + wiring tests for the demo run-history seeder (PURE — DB monkeypatched away).

Covers the safety contract of app/repositories/demo_runs.ensure_demo_run_history:
  * a NON-demo tenant never opens a DB session (fail closed — real customers are never seeded);
  * a sparse demo tenant gets exactly the (agent, day) plan inserted — existing days untouched;
  * a dense window plans nothing; future days are never fabricated;
  * any failure is swallowed (a seeding error can never break the timeseries endpoint);
  * seeded run ids are deterministic (the ON CONFLICT idempotency key).

Plus the route-level wiring test: GET /v1/org/kpis/timeseries calls the seeder with the clamped
window BEFORE reading runs, and the seeded history round-trips through the UNMODIFIED
`aggregate_kpis_timeseries` into ~30 daily points per charted KPI (the in-process smoke).
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.demo import DEMO_TENANTS
from app.org import demo_history
from app.org.kpis import _AGENT_KPIS
from app.repositories import demo_runs

CANYONRIDGE = DEMO_TENANTS["canyonridge"].tenant_id
NON_DEMO_TENANT = uuid.UUID("99999999-9999-9999-9999-999999999999")

# A fixed, fully-in-the-past window (June 2026) so the today-clamp never trims it.
START = date(2026, 6, 1)
END = date(2026, 6, 30)
WINDOW = 30

ALL_KPI_KEYS = {key for key, _, _, _, _, _ in _AGENT_KPIS}


@asynccontextmanager
async def _fake_session(tenant_id):
    yield object()


def _no_session_allowed(calls: list):
    @asynccontextmanager
    async def _session(tenant_id):
        calls.append(tenant_id)
        yield object()

    return _session


class TestDemoGate:
    async def test_non_demo_tenant_never_opens_a_session(self, monkeypatch) -> None:
        opened: list = []
        monkeypatch.setattr(demo_runs, "tenant_session", _no_session_allowed(opened))
        seeded = await demo_runs.ensure_demo_run_history(NON_DEMO_TENANT, start=START, end=END)
        assert seeded == 0
        assert opened == []  # fail closed: not even a read for a non-demo tenant

    async def test_every_demo_tenant_id_passes_the_gate(self) -> None:
        for tenant in DEMO_TENANTS.values():
            assert demo_runs._demo_tenant(tenant.tenant_id) is tenant
        assert demo_runs._demo_tenant(NON_DEMO_TENANT) is None


class TestSeedPlanExecution:
    async def test_sparse_demo_tenant_inserts_exactly_the_missing_agent_days(
        self, monkeypatch
    ) -> None:
        existing = {"booking": {START, START + timedelta(days=1)}}
        inserted: list[tuple[str, date]] = []

        async def _fake_days(session, *, start, end):
            return existing

        async def _fake_insert(session, *, run_id, agent, day, created_by, result):
            assert created_by == DEMO_TENANTS["canyonridge"].admin_user_id
            assert result == demo_history.demo_run_history("canyonridge", agent, day)
            inserted.append((agent, day))

        monkeypatch.setattr(demo_runs, "tenant_session", _fake_session)
        monkeypatch.setattr(demo_runs.runs_repo, "list_succeeded_run_days_by_agent", _fake_days)
        monkeypatch.setattr(demo_runs, "_insert_seeded_run", _fake_insert)

        seeded = await demo_runs.ensure_demo_run_history(CANYONRIDGE, start=START, end=END)
        assert seeded == len(inserted) == len(demo_history.CHARTED_AGENTS) * WINDOW - 2
        assert ("booking", START) not in inserted  # real (agent, day) rows are never re-seeded
        assert ("financial", START) in inserted

    async def test_wide_axis_window_is_bounded_to_the_seed_horizon(self, monkeypatch) -> None:
        """A caller-supplied 366-day timeseries window must NEVER plan a year of inserts in the
        foreground GET — the seed window is capped at _SEED_HORIZON_DAYS regardless of the axis."""
        inserted: list[tuple[str, date]] = []

        async def _fake_days(session, *, start, end):
            # The bound applies BEFORE the coverage probe: the probed window is already capped.
            assert (end - start).days <= demo_runs._SEED_HORIZON_DAYS
            return {}

        async def _fake_insert(session, *, run_id, agent, day, created_by, result):
            inserted.append((agent, day))

        monkeypatch.setattr(demo_runs, "tenant_session", _fake_session)
        monkeypatch.setattr(demo_runs.runs_repo, "list_succeeded_run_days_by_agent", _fake_days)
        monkeypatch.setattr(demo_runs, "_insert_seeded_run", _fake_insert)

        wide_start = END - timedelta(days=366)
        seeded = await demo_runs.ensure_demo_run_history(CANYONRIDGE, start=wide_start, end=END)
        max_rows = len(demo_history.CHARTED_AGENTS) * (demo_runs._SEED_HORIZON_DAYS + 1)
        assert 0 < seeded == len(inserted) <= max_rows
        assert min(day for _, day in inserted) >= END - timedelta(days=demo_runs._SEED_HORIZON_DAYS)

    async def test_dense_window_inserts_nothing(self, monkeypatch) -> None:
        dense = {"booking": {START + timedelta(days=i) for i in range(18)}}  # 60% coverage

        async def _fake_days(session, *, start, end):
            return dense

        async def _boom(session, **kwargs):  # pragma: no cover - must not be reached
            raise AssertionError("dense coverage must not insert")

        monkeypatch.setattr(demo_runs, "tenant_session", _fake_session)
        monkeypatch.setattr(demo_runs.runs_repo, "list_succeeded_run_days_by_agent", _fake_days)
        monkeypatch.setattr(demo_runs, "_insert_seeded_run", _boom)

        assert await demo_runs.ensure_demo_run_history(CANYONRIDGE, start=START, end=END) == 0

    async def test_future_days_are_never_fabricated(self, monkeypatch) -> None:
        inserted_days: list[date] = []

        async def _fake_days(session, *, start, end):
            return {}

        async def _fake_insert(session, *, run_id, agent, day, created_by, result):
            inserted_days.append(day)

        monkeypatch.setattr(demo_runs, "tenant_session", _fake_session)
        monkeypatch.setattr(demo_runs.runs_repo, "list_succeeded_run_days_by_agent", _fake_days)
        monkeypatch.setattr(demo_runs, "_insert_seeded_run", _fake_insert)

        today = date.today()
        await demo_runs.ensure_demo_run_history(
            CANYONRIDGE, start=today - timedelta(days=2), end=today + timedelta(days=5)
        )
        assert inserted_days and max(inserted_days) <= today

    async def test_all_future_window_is_a_no_op(self, monkeypatch) -> None:
        opened: list = []
        monkeypatch.setattr(demo_runs, "tenant_session", _no_session_allowed(opened))
        tomorrow = date.today() + timedelta(days=1)
        seeded = await demo_runs.ensure_demo_run_history(
            CANYONRIDGE, start=tomorrow, end=tomorrow + timedelta(days=7)
        )
        assert seeded == 0 and opened == []

    async def test_a_seeding_failure_is_swallowed_never_raised(self, monkeypatch) -> None:
        async def _explode(session, *, start, end):
            raise RuntimeError("db is down")

        monkeypatch.setattr(demo_runs, "tenant_session", _fake_session)
        monkeypatch.setattr(demo_runs.runs_repo, "list_succeeded_run_days_by_agent", _explode)
        assert await demo_runs.ensure_demo_run_history(CANYONRIDGE, start=START, end=END) == 0


class TestSeededRunId:
    def test_id_is_deterministic_per_tenant_agent_day(self) -> None:
        a = demo_runs.seeded_run_id("canyonridge", "booking", START)
        b = demo_runs.seeded_run_id("canyonridge", "booking", START)
        assert a == b  # re-running the seed hits ON CONFLICT, never a duplicate row

    def test_id_differs_across_the_key_dimensions(self) -> None:
        base = demo_runs.seeded_run_id("canyonridge", "booking", START)
        assert base != demo_runs.seeded_run_id("apex", "booking", START)
        assert base != demo_runs.seeded_run_id("canyonridge", "routing", START)
        assert base != demo_runs.seeded_run_id("canyonridge", "booking", END)


class TestRouteWiring:
    """GET /v1/org/kpis/timeseries seeds BEFORE reading, and the seeded rows flow through the
    unmodified aggregator into a full ~30-day chart — the end-to-end in-process smoke."""

    def _client(self) -> TestClient:
        from app.main import app

        return TestClient(app, raise_server_exceptions=False)

    def _admin_headers(self) -> dict[str, str]:
        from app.security import create_token

        token = create_token(
            tenant_id=CANYONRIDGE,
            user_id=DEMO_TENANTS["canyonridge"].admin_user_id,
            email=DEMO_TENANTS["canyonridge"].admin_email,
            role="admin",
            department=None,
        )
        return {"Authorization": f"Bearer {token}"}

    def test_route_seeds_then_serves_thirty_daily_points_per_kpi(self, monkeypatch) -> None:
        from app.api import routes_org
        from app.repositories import org as org_repo
        from app.repositories import runs as runs_repo

        seed_calls: list[tuple[uuid.UUID, date, date]] = []

        async def _fake_ensure(tenant_id, *, start, end):
            seed_calls.append((tenant_id, start, end))
            return 0

        async def _fake_runs(session, *, start, end):
            # The seeded history a real DB read would return after ensure_demo_run_history ran.
            plan = demo_history.plan_seed_runs("canyonridge", {}, start, end)
            return [{"date": day, "agent": agent, "result": result} for agent, day, result in plan]

        async def _fake_overview(tenant_id):
            return {
                "company": {"name": "Canyon Ridge Mechanical", "employee_count": 38},
                "departments": [
                    {"key": "front_office", "name": "Front Office", "color": "#8b5cf6"},
                    {"key": "dispatch", "name": "Dispatch", "color": "#f59e0b"},
                    {"key": "field", "name": "Field", "color": "#10b981"},
                    {"key": "finance", "name": "Finance", "color": "#3b82f6"},
                    {"key": "warehouse", "name": "Warehouse", "color": "#ef4444"},
                ],
            }

        async def _noop_seed(tenant_id):
            return None

        monkeypatch.setattr(demo_runs, "ensure_demo_run_history", _fake_ensure)
        monkeypatch.setattr(runs_repo, "list_succeeded_runs_in_range", _fake_runs)
        monkeypatch.setattr(org_repo, "ensure_seeded", _noop_seed)
        monkeypatch.setattr(org_repo, "get_overview", _fake_overview)
        monkeypatch.setattr(routes_org, "tenant_session", _fake_session)

        resp = self._client().get("/v1/org/kpis/timeseries", headers=self._admin_headers())
        assert resp.status_code == 200, resp.text

        # The seeder ran for the caller's tenant over the route's default clamped window.
        today = date.today()
        assert seed_calls == [(CANYONRIDGE, today - timedelta(days=29), today)]

        payload = resp.json()
        assert len(payload["dates"]) == 30
        assert {s["key"] for s in payload["series"]} == ALL_KPI_KEYS
        for series in payload["series"]:
            assert len(series["points"]) == 30
            assert all(p["value"] is not None for p in series["points"]), series["key"]

    def test_department_scoped_login_is_still_refused(self, monkeypatch) -> None:
        from app.security import create_token

        seed_calls: list = []

        async def _fake_ensure(tenant_id, *, start, end):  # pragma: no cover - must not run
            seed_calls.append(tenant_id)
            return 0

        monkeypatch.setattr(demo_runs, "ensure_demo_run_history", _fake_ensure)
        token = create_token(
            tenant_id=CANYONRIDGE,
            user_id=uuid.uuid4(),
            email="person1@example.com",
            role="analyst",
            department="dispatch",
        )
        resp = self._client().get(
            "/v1/org/kpis/timeseries", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 403
        assert seed_calls == []  # the auth gate fires before any seeding
