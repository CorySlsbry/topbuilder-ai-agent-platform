"""Unit + property tests for the deterministic dispatch-routing engine.

Hand-computed oracle (Manhattan zones, 3 min/unit, 3 techs, 6 jobs):
  optimized assignment J1,J2->T1 · J3,J4->T2 · J5->T3 · J6 unassigned (no electrical skill)
  optimized drive = 18 min · naive round-robin baseline = 78 min · saved = 60 min/day.
"""
from __future__ import annotations

from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from app.agents.routing import analytics as a
from app.agents.routing.models import DispatchData, DispatchJob, FieldTech

AS_OF = date(2026, 6, 8)


def _job(jid: str, x: int, y: int, skill: str, trade: str | None = None) -> DispatchJob:
    return DispatchJob(
        id=jid, customer_name=f"Customer {jid}", trade=trade or skill, job_type="service",
        x=x, y=y, duration_min=60, priority=5, required_skill=skill,
        window_start_min=480, window_end_min=1020, status="scheduled",
    )


def _scenario() -> DispatchData:
    techs = [
        FieldTech(id="T1", name="Alex", skills=["hvac"], home_x=0, home_y=0, shift_start_min=480, shift_end_min=1020),
        FieldTech(id="T2", name="Bri", skills=["plumbing"], home_x=10, home_y=10, shift_start_min=480, shift_end_min=1020),
        FieldTech(id="T3", name="Cy", skills=["hvac"], home_x=0, home_y=10, shift_start_min=480, shift_end_min=1020),
    ]
    jobs = [
        _job("J1", 1, 0, "hvac"),
        _job("J2", 2, 0, "hvac"),
        _job("J3", 10, 9, "plumbing"),
        _job("J4", 9, 10, "plumbing"),
        _job("J5", 0, 9, "hvac"),
        _job("J6", 5, 5, "electrical"),
    ]
    return DispatchData(as_of=AS_OF, jobs=jobs, technicians=techs)


class TestRoutingEngine:
    def test_totals(self) -> None:
        t = a.analyze(_scenario()).totals
        assert (t.jobs, t.assigned, t.unassigned, t.techs_used) == (6, 5, 1, 3)
        assert (t.drive_minutes_optimized, t.drive_minutes_baseline, t.drive_minutes_saved) == (18, 78, 60)

    def test_assignments(self) -> None:
        by = {s.job_id: s.tech_id for s in a.analyze(_scenario()).suggestions}
        assert by == {"J1": "T1", "J2": "T1", "J3": "T2", "J4": "T2", "J5": "T3"}

    def test_unassigned_no_skill(self) -> None:
        unassigned = {u.job_id: u.reason.lower() for u in a.analyze(_scenario()).unassigned}
        assert "electrical" in unassigned["J6"]
        assert "skill" in unassigned["J6"]

    def test_sequence_and_arrival(self) -> None:
        by = {s.job_id: s for s in a.analyze(_scenario()).suggestions}
        assert (by["J1"].sequence, by["J2"].sequence) == (1, 2)  # both T1's stops, in order
        assert by["J1"].arrival_min == 483  # 08:00 + 3min drive

    def test_inputs_hash_stable_and_hex(self) -> None:
        h1 = a.analyze(_scenario()).inputs_hash
        h2 = a.analyze(_scenario()).inputs_hash
        assert h1 == h2 and len(h1) == 64


class TestProperties:
    @given(st.lists(st.tuples(st.integers(0, 20), st.integers(0, 20)), min_size=1, max_size=8))
    def test_optimized_never_worse_than_baseline(self, coords: list[tuple[int, int]]) -> None:
        techs = [FieldTech(id="T1", name="A", skills=["hvac"], home_x=0, home_y=0, shift_start_min=0, shift_end_min=1440)]
        jobs = [
            _job(f"J{i}", x, y, "hvac") for i, (x, y) in enumerate(coords)
        ]
        t = a.analyze(DispatchData(as_of=AS_OF, jobs=jobs, technicians=techs)).totals
        # With a single tech, optimized re-sequences the same stops; saved is never negative.
        assert t.drive_minutes_saved >= 0
        assert t.drive_minutes_optimized <= t.drive_minutes_baseline
