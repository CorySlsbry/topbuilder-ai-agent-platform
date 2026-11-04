"""Unit + property tests for the deterministic dispatch TRIAGE engine (P1/P2/P3 + revenue-rank + board).

Hand-computed oracle (Manhattan zones, 3 min/unit, revenue ref $1,000 ticket / 100% conversion):

Techs:
  Aaron Scott (hvac)   home (1,0)  avg_ticket $1,400=140_000c  conversion 60%
    revenue_score = (min(10000,14000)=10000 + 6000) // 2                       = 8000
  Ben Lee (hvac)       home (2,0)  avg_ticket $600=60_000c     conversion 30%
    revenue_score = (6000 + 3000) // 2                                          = 4500
  Cy Park (plumbing)   home (10,10) avg_ticket $900=90_000c    conversion 40%
  (no electrical tech on the roster)

P1 no-heat job J_NOHEAT at (0,0):
  Aaron drive = |1-0|+|0-0| = 1 unit * 3 = 3min ; prox_bp = (120-3)*10000//120 = 9750
    score = (3000*10000 + 3000*9750 + 4000*8000) // 10000 = 91_250_000 // 10000 = 9125
  Ben   drive = |2-0|+|0-0| = 2 units * 3 = 6min ; prox_bp = (120-6)*10000//120 = 9500
    score = (3000*10000 + 3000*9500 + 4000*4500) // 10000 = 76_500_000 // 10000 = 7650
  => Aaron (9125) outranks Ben (7650): skilled + high-revenue + nearer wins.
"""
from __future__ import annotations

from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from app.agents.routing import triage as tr
from app.agents.routing.models import P1, P2, P3, DispatchData, DispatchJob, FieldTech

AS_OF = date(2026, 6, 16)


def _job(
    jid: str,
    *,
    skill: str,
    job_type: str,
    severity: str = "",
    x: int = 0,
    y: int = 0,
    duration_min: int = 60,
    revenue_cents: int = 0,
    scheduled_date: str = "",
    trade: str | None = None,
) -> DispatchJob:
    return DispatchJob(
        id=jid, customer_name=f"Customer {jid}", trade=trade or skill, job_type=job_type,
        x=x, y=y, duration_min=duration_min, priority=5, required_skill=skill,
        window_start_min=480, window_end_min=1020, status="scheduled",
        severity=severity, scheduled_date=scheduled_date, revenue_cents=revenue_cents,
    )


def _aaron() -> FieldTech:
    return FieldTech(
        id="T_AARON", name="Aaron Scott", skills=["hvac"], home_x=1, home_y=0,
        shift_start_min=480, shift_end_min=1020, avg_ticket_cents=140_000, conversion_pct=60,
    )


def _ben() -> FieldTech:
    return FieldTech(
        id="T_BEN", name="Ben Lee", skills=["hvac"], home_x=2, home_y=0,
        shift_start_min=480, shift_end_min=1020, avg_ticket_cents=60_000, conversion_pct=30,
    )


def _cy() -> FieldTech:
    return FieldTech(
        id="T_CY", name="Cy Park", skills=["plumbing"], home_x=10, home_y=10,
        shift_start_min=480, shift_end_min=1020, avg_ticket_cents=90_000, conversion_pct=40,
    )


def _scenario() -> DispatchData:
    techs = [_aaron(), _ben(), _cy()]
    jobs = [
        # P1 emergency, no heat — at the origin (Aaron & Ben both hvac)
        _job("J_NOHEAT", skill="hvac", job_type="no_heat", severity="emergency", x=0, y=0,
             revenue_cents=80_000, duration_min=90),
        # P2 same-day comfort leak (plumbing)
        _job("J_LEAK", skill="plumbing", job_type="leak", x=10, y=9, revenue_cents=45_000),
        # P3 maintenance tune-up (hvac)
        _job("J_TUNE", skill="hvac", job_type="maintenance", x=3, y=0, revenue_cents=20_000),
        # P3 thermostat (hvac) — same priority as tune-up but HIGHER revenue -> sorts ahead within P3
        _job("J_STAT", skill="hvac", job_type="thermostat", x=4, y=0, revenue_cents=30_000),
        # unassignable: no electrical tech on the roster
        _job("J_PANEL", skill="electrical", job_type="panel", x=5, y=5, severity="emergency",
             revenue_cents=120_000),
    ]
    return DispatchData(as_of=AS_OF, jobs=jobs, technicians=techs)


class TestClassifyPriority:
    def test_explicit_severity_emergency_is_p1(self) -> None:
        j = _job("x", skill="hvac", job_type="maintenance", severity="emergency")
        assert tr.classify_priority(j) == (P1, "severity")

    def test_job_type_no_heat_is_p1_when_no_severity(self) -> None:
        j = _job("x", skill="hvac", job_type="no_heat")
        assert tr.classify_priority(j) == (P1, "job_type")

    def test_comfort_leak_is_p2(self) -> None:
        j = _job("x", skill="plumbing", job_type="leak")
        assert tr.classify_priority(j) == (P2, "job_type")

    def test_maintenance_is_p3(self) -> None:
        j = _job("x", skill="hvac", job_type="maintenance")
        assert tr.classify_priority(j) == (P3, "job_type")

    def test_unknown_defaults_to_p3(self) -> None:
        j = _job("x", skill="hvac", job_type="zzz_unknown")
        assert tr.classify_priority(j) == (P3, "default")


class TestRevenueScore:
    def test_aaron_revenue_score(self) -> None:
        assert tr.revenue_score_bp(_aaron()) == 8000

    def test_ben_revenue_score(self) -> None:
        assert tr.revenue_score_bp(_ben()) == 4500

    def test_higher_ticket_and_conversion_never_scores_lower(self) -> None:
        assert tr.revenue_score_bp(_aaron()) > tr.revenue_score_bp(_ben())


class TestRankTechs:
    def test_skilled_high_revenue_near_tech_wins(self) -> None:
        job = _scenario().jobs[0]  # J_NOHEAT at (0,0)
        ranks = tr.rank_techs(job, [_aaron(), _ben(), _cy()])
        # only the two hvac techs are eligible; Cy (plumbing) is filtered out
        assert [r.tech_id for r in ranks] == ["T_AARON", "T_BEN"]
        assert (ranks[0].score_bp, ranks[1].score_bp) == (9125, 7650)
        assert ranks[0].drive_minutes == 3

    def test_no_eligible_tech_returns_empty(self) -> None:
        job = _job("e", skill="electrical", job_type="panel")
        assert tr.rank_techs(job, [_aaron(), _ben(), _cy()]) == []


class TestTriageAnalysis:
    def test_totals(self) -> None:
        t = tr.analyze_triage(_scenario()).totals
        # J_NOHEAT=P1, J_PANEL=P1(emergency severity) ; J_LEAK=P2 ; J_TUNE,J_STAT=P3
        assert (t.jobs, t.p1, t.p2, t.p3) == (5, 2, 1, 2)
        assert (t.assignable, t.needs_human) == (4, 1)

    def test_p1_sorts_first(self) -> None:
        triaged = tr.analyze_triage(_scenario()).triaged
        # P1 jobs lead the list; ordered within P1 by revenue desc (J_PANEL $1,200 > J_NOHEAT $800)
        assert [j.job_id for j in triaged[:2]] == ["J_PANEL", "J_NOHEAT"]
        assert all(j.priority == P1 for j in triaged[:2])
        # last two are the P3 jobs, higher-revenue thermostat ahead of the tune-up
        assert [j.job_id for j in triaged[-2:]] == ["J_STAT", "J_TUNE"]

    def test_recommended_tech_is_aaron_for_no_heat(self) -> None:
        triaged = {j.job_id: j for j in tr.analyze_triage(_scenario()).triaged}
        assert triaged["J_NOHEAT"].recommended_tech_id == "T_AARON"
        assert triaged["J_NOHEAT"].assignable is True

    def test_unassigned_queue_is_panel_only(self) -> None:
        analysis = tr.analyze_triage(_scenario())
        assert analysis.unassigned_queue == ["J_PANEL"]
        panel = next(j for j in analysis.triaged if j.job_id == "J_PANEL")
        assert panel.assignable is False
        assert "electrical" in panel.reason and "human" in panel.reason

    def test_inputs_hash_stable_and_hex(self) -> None:
        h1 = tr.analyze_triage(_scenario()).inputs_hash
        h2 = tr.analyze_triage(_scenario()).inputs_hash
        assert h1 == h2 and len(h1) == 64


class TestThreeDayBoard:
    def test_board_has_three_days_starting_as_of(self) -> None:
        board = tr.analyze_triage(_scenario()).board
        assert [d.day for d in board] == [
            "2026-06-16", "2026-06-17", "2026-06-18",
        ]

    def test_capacity_sums_all_tech_shift_minutes(self) -> None:
        # 3 techs each 480..1020 = 540 min -> capacity 1620 every day
        board = tr.analyze_triage(_scenario()).board
        assert all(d.capacity_min == 1620 for d in board)

    def test_day_one_booked_sums_durations(self) -> None:
        # all 5 jobs default to as_of (blank scheduled_date): 90+60+60+60+60 = 330 booked on day 1
        day1 = tr.analyze_triage(_scenario()).board[0]
        assert (day1.booked_min, day1.job_count) == (330, 5)
        assert day1.free_min == 1620 - 330  # 1290
        assert day1.over_capacity_min == 0
        assert day1.utilization_pct == 330 * 100 // 1620  # 20

    def test_future_days_are_empty_when_no_jobs_scheduled(self) -> None:
        board = tr.analyze_triage(_scenario()).board
        assert (board[1].booked_min, board[1].job_count) == (0, 0)
        assert board[1].free_min == 1620

    def test_scheduled_date_routes_job_to_its_day(self) -> None:
        data = DispatchData(
            as_of=AS_OF,
            jobs=[_job("F", skill="hvac", job_type="maintenance", duration_min=120,
                       scheduled_date="2026-06-18")],
            technicians=[_aaron()],  # capacity 540/day
        )
        board = tr.analyze_triage(data).board
        assert board[0].booked_min == 0          # nothing on as_of
        assert board[2].booked_min == 120         # lands on day 3
        assert board[2].job_count == 1

    def test_over_capacity_is_flagged(self) -> None:
        # one tech (540 cap), one 600-min job -> over by 60, utilization 111%
        data = DispatchData(
            as_of=AS_OF,
            jobs=[_job("BIG", skill="hvac", job_type="install", duration_min=600)],
            technicians=[_aaron()],
        )
        day1 = tr.analyze_triage(data).board[0]
        assert (day1.capacity_min, day1.booked_min) == (540, 600)
        assert day1.over_capacity_min == 60
        assert day1.free_min == 0
        assert day1.utilization_pct == 111  # 600*100//540

    def test_zero_shift_tech_is_unavailable_gray_block(self) -> None:
        off = FieldTech(id="T_OFF", name="Off Tech", skills=["hvac"], home_x=0, home_y=0,
                        shift_start_min=600, shift_end_min=600)  # zero-length shift
        data = DispatchData(as_of=AS_OF, jobs=[], technicians=[_aaron(), off])
        day1 = tr.analyze_triage(data).board[0]
        assert day1.unavailable_tech_ids == ["T_OFF"]
        assert day1.capacity_min == 540  # only Aaron contributes capacity


class TestSummitFixtureOracle:
    """Exercise the Summit-shaped triage fixture end-to-end through the engine (no DB/LLM).

    Fixture: 8 jobs (4 P1 emergencies incl. a no-heat), trades hvac/plumbing/install/electrical/drains;
    techs incl. Aaron Scott (top revenue). Board = 4 techs x 540min = 2160 capacity/day; the install
    (240min) is scheduled on day 3 (2026-06-18).
    """

    @staticmethod
    def _analysis():
        import asyncio

        from app.agents.routing.data import assemble_triage_data
        from app.integrations.dispatch.fixture_client import FixtureDispatchClient

        async def run():
            data = await assemble_triage_data(FixtureDispatchClient(), as_of=AS_OF)
            return tr.analyze_triage(data)

        return asyncio.run(run())

    def test_totals(self) -> None:
        t = self._analysis().totals
        assert (t.jobs, t.p1, t.p2, t.p3) == (8, 4, 1, 3)
        assert (t.assignable, t.needs_human) == (7, 1)

    def test_p1_emergencies_lead_revenue_ranked(self) -> None:
        triaged = self._analysis().triaged
        # P1s first, ordered by revenue desc: S02 $1,100 > S07 $950 > S01 $850 > S08 $670
        assert [j.job_id for j in triaged[:4]] == ["S02", "S07", "S01", "S08"]
        assert all(j.priority == P1 for j in triaged[:4])

    def test_no_heat_p1_goes_to_aaron_scott(self) -> None:
        s01 = next(j for j in self._analysis().triaged if j.job_id == "S01")
        assert s01.priority_label == "P1"
        assert s01.recommended_tech_name == "Aaron Scott"  # skilled + top revenue + near
        # Aaron outranks the other eligible hvac techs
        assert [c.tech_id for c in s01.candidates][0] == "T_AARON"

    def test_electrical_panel_needs_a_human(self) -> None:
        analysis = self._analysis()
        assert analysis.unassigned_queue == ["S07"]  # no electrical tech on the roster
        s07 = next(j for j in analysis.triaged if j.job_id == "S07")
        assert s07.assignable is False

    def test_three_day_board_sums(self) -> None:
        board = self._analysis().board
        assert [d.day for d in board] == ["2026-06-16", "2026-06-17", "2026-06-18"]
        assert all(d.capacity_min == 2160 for d in board)  # 4 techs x 540min
        # the 240-min install sits on day 3 (its scheduled_date)
        assert board[2].job_count == 1 and board[2].booked_min == 240
        # day 1 holds the other 7 jobs
        assert board[0].job_count == 7


class TestProperties:
    @given(
        st.lists(
            st.sampled_from(["no_heat", "emergency", "leak", "comfort", "maintenance",
                             "thermostat", "zzz_unknown"]),
            min_size=1, max_size=12,
        )
    )
    def test_every_job_classified_into_a_known_priority(self, job_types: list[str]) -> None:
        jobs = [_job(f"J{i}", skill="hvac", job_type=jt) for i, jt in enumerate(job_types)]
        data = DispatchData(as_of=AS_OF, jobs=jobs, technicians=[_aaron()])
        analysis = tr.analyze_triage(data)
        assert all(j.priority in (P1, P2, P3) for j in analysis.triaged)
        # the triaged list is always non-decreasing in priority (P1 before P2 before P3)
        prios = [j.priority for j in analysis.triaged]
        assert prios == sorted(prios)
        # counts partition the jobs
        t = analysis.totals
        assert t.p1 + t.p2 + t.p3 == t.jobs == len(jobs)

    @given(st.integers(min_value=0, max_value=10000))
    def test_board_free_and_over_are_mutually_exclusive(self, duration: int) -> None:
        data = DispatchData(
            as_of=AS_OF,
            jobs=[_job("J", skill="hvac", job_type="install", duration_min=duration)],
            technicians=[_aaron()],  # capacity 540
        )
        d = tr.analyze_triage(data).board[0]
        # exactly one of free / over is non-zero (or both zero at the exact boundary)
        assert d.free_min == 0 or d.over_capacity_min == 0
        assert d.free_min - d.over_capacity_min == d.capacity_min - d.booked_min
