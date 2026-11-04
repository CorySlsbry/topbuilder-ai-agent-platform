"""Oracle tests for the rolling-capacity SERVICE assembly + projection result.

The pure engine (``capacity.py``) is tested independently in ``test_capacity.py``; here we test the
wiring built on top of it: ``build_capacity_run`` (assemble inputs -> engine -> packaged result with a
stable ``inputs_hash``), ``capacity_schemas.build_result`` (the API roll-up + the faster/slower "pace"
read), and the Canyon Ridge fixture story (a tech getting faster + a tech trending into overtime + a
same-trade tech with slack to absorb it).

Two oracle styles, deliberately independent of the engine internals:
  * a SYNTHETIC scenario where each tech's only job type has samples that all equal the provided
    baseline, so the credibility blend collapses to that exact value -> the projected weekly hours are
    plain multiplication we hand-compute;
  * the REAL fixtures, asserted on direction + structure (faster/slower, who is over capacity, who can
    absorb it) so the demo story is locked without re-deriving blended floats.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from app.agents.workforce.capacity import AssignedJob, CompletedJob
from app.agents.workforce.capacity_data import CapacityData, _fixture_capacity_data
from app.agents.workforce.capacity_schemas import build_result, pace_read
from app.agents.workforce.capacity_service import build_capacity_run
from app.agents.workforce.models import Technician

AS_OF = date(2026, 6, 30)
FIXTURE_AS_OF = date(2026, 6, 30)


# --------------------------------------------------------------------------------------------
# pace_read — the plain-language efficiency read (negative delta => faster than baseline)
# --------------------------------------------------------------------------------------------
class TestPaceRead:
    @pytest.mark.parametrize(
        "delta, expected",
        [(-1.0, "faster"), (-0.3, "faster"), (-0.25, "on baseline"), (0.0, "on baseline"),
         (0.25, "on baseline"), (0.3, "slower"), (2.5, "slower")],
    )
    def test_known(self, delta: float, expected: str) -> None:
        assert pace_read(delta) == expected


# --------------------------------------------------------------------------------------------
# build_capacity_run — SYNTHETIC scenario with exact, hand-computed projected hours
# --------------------------------------------------------------------------------------------
def _synthetic_data() -> CapacityData:
    """Each tech's only job type has all samples == the provided baseline, so the credibility blend
    collapses to that exact value (rolling == baseline => estimate == baseline). Then projected hours
    are plain multiplication: t1 = 5*9 = 45h (>40 -> 5h OT); t2 = 3*9 = 27h (slack)."""
    completed = (
        [CompletedJob("t1", "install", "hvac", 9.0, date(2026, 6, 20))] * 4
        + [CompletedJob("t2", "install", "hvac", 9.0, date(2026, 6, 20))] * 4
    )
    assigned = (
        [AssignedJob("t1", "install", "hvac")] * 5
        + [AssignedJob("t2", "install", "hvac")] * 3
    )
    techs = [
        Technician("t1", "Tech One", "hvac", 40, 50, 1.5),
        Technician("t2", "Tech Two", "hvac", 40, 50, 1.5),
    ]
    return CapacityData(
        as_of=AS_OF,
        completed_jobs=completed,
        assigned_jobs=assigned,
        technicians=techs,
        baselines={"install": 9.0},
    )


class TestBuildCapacityRunSynthetic:
    def test_estimate_collapses_to_baseline_when_samples_equal_it(self) -> None:
        run = build_capacity_run(_synthetic_data())
        by_key = {(d.technician_id, d.job_type): d for d in run.durations}
        # rolling == baseline == 9.0 -> the blend leaves the estimate exactly on the baseline.
        for tech in ("t1", "t2"):
            d = by_key[(tech, "install")]
            assert d.rolling_hours == pytest.approx(9.0)
            assert d.baseline_hours == pytest.approx(9.0)
            assert d.estimate_hours == pytest.approx(9.0)
            assert d.efficiency_delta_hours == pytest.approx(0.0)

    def test_overloaded_tech_projects_exact_overtime(self) -> None:
        run = build_capacity_run(_synthetic_data())
        t1 = next(p for p in run.projections if p.technician_id == "t1")
        assert t1.projected_hours == pytest.approx(45.0)  # 5 jobs * 9.0h
        assert t1.overtime_hours == pytest.approx(5.0)     # 45 - 40 contracted

    def test_overtime_routes_to_the_same_trade_tech_with_slack(self) -> None:
        run = build_capacity_run(_synthetic_data())
        t1 = next(p for p in run.projections if p.technician_id == "t1")
        assert t1.redistribute_to == ["t2"]  # t2 projects 27h << 40h, same trade

    def test_slack_tech_has_no_overtime(self) -> None:
        run = build_capacity_run(_synthetic_data())
        t2 = next(p for p in run.projections if p.technician_id == "t2")
        assert t2.projected_hours == pytest.approx(27.0)  # 3 jobs * 9.0h
        assert t2.overtime_hours == pytest.approx(0.0)
        assert t2.redistribute_to == []

    def test_projections_sorted_overtime_first(self) -> None:
        run = build_capacity_run(_synthetic_data())
        assert [p.technician_id for p in run.projections] == ["t1", "t2"]

    def test_inputs_hash_is_stable_and_deterministic(self) -> None:
        a = build_capacity_run(_synthetic_data())
        b = build_capacity_run(_synthetic_data())
        assert a.inputs_hash == b.inputs_hash
        assert len(a.inputs_hash) == 64  # sha256 hex


# --------------------------------------------------------------------------------------------
# build_result — the API roll-up over the synthetic run
# --------------------------------------------------------------------------------------------
class TestBuildResult:
    def test_totals_roll_up_the_projections(self) -> None:
        run = build_capacity_run(_synthetic_data())
        result = build_result(
            as_of=run.as_of,
            durations=run.durations,
            projections=run.projections,
            inputs_hash=run.inputs_hash,
            narrative="x",
            analysis_timestamp=datetime(2026, 6, 30, 12, 0, 0),
        )
        assert result.totals.technicians == 2
        assert result.totals.duration_pairs == 2          # (t1, install) + (t2, install)
        assert result.totals.techs_over_capacity == 1     # only t1
        assert result.totals.total_overtime_hours == pytest.approx(5.0)
        assert result.inputs_hash == run.inputs_hash
        # the pace read is surfaced on every duration row
        assert {d.pace for d in result.durations} == {"on baseline"}


# --------------------------------------------------------------------------------------------
# Canyon Ridge FIXTURE story — direction + structure oracles (the visible demo)
# --------------------------------------------------------------------------------------------
def _fixture_run():
    return build_capacity_run(_fixture_capacity_data(FIXTURE_AS_OF))


class TestCanyonRidgeFixtureStory:
    def test_only_the_relevant_active_hvac_techs_are_covered(self) -> None:
        run = _fixture_run()
        # The fixtures involve t-h1, t-h2, t-h3 (and only those appear in completed/assigned).
        assert {p.technician_id for p in run.projections} == {"t-h1", "t-h2", "t-h3"}

    def test_alice_is_getting_faster_than_baseline_on_ac_install(self) -> None:
        run = _fixture_run()
        d = next(
            x for x in run.durations if x.technician_id == "t-h1" and x.job_type == "ac_install"
        )
        # Recent runs trend to ~5h against the 8.0h ac_install baseline -> faster.
        assert d.baseline_hours == pytest.approx(8.0)
        assert d.estimate_hours < d.baseline_hours
        assert d.efficiency_delta_hours < 0
        assert pace_read(d.efficiency_delta_hours) == "faster"

    def test_ben_is_slower_than_baseline_on_ac_install(self) -> None:
        run = _fixture_run()
        d = next(
            x for x in run.durations if x.technician_id == "t-h2" and x.job_type == "ac_install"
        )
        # Steady ~9-9.5h against the 8.0h baseline -> slower.
        assert d.estimate_hours > d.baseline_hours
        assert pace_read(d.efficiency_delta_hours) == "slower"

    def test_ben_projects_into_overtime_next_week(self) -> None:
        run = _fixture_run()
        ben = next(p for p in run.projections if p.technician_id == "t-h2")
        # 5 installs * ~9h each >> 40h contracted.
        assert ben.job_count == 5
        assert ben.overtime_hours > 0

    def test_carlos_has_slack_and_absorbs_bens_overflow(self) -> None:
        run = _fixture_run()
        ben = next(p for p in run.projections if p.technician_id == "t-h2")
        carlos = next(p for p in run.projections if p.technician_id == "t-h3")
        assert carlos.overtime_hours == pytest.approx(0.0)
        assert "t-h3" in ben.redistribute_to

    def test_fixture_inputs_hash_is_stable_across_assembles(self) -> None:
        assert _fixture_run().inputs_hash == _fixture_run().inputs_hash
