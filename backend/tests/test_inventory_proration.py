"""Unit + property tests for the partial-consumable cost proration engine (ADR 0003 — pure).

Every asserted number is a hand-computed, independent oracle. The headline scenarios are the ones in
the build spec: a $300 vent spool split four ways evenly ($75 each), and a copper lot split by linear
feet [10/15/25] (proportional, remainder cent to the largest-share job).
"""
from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.agents.inventory import proration as pr
from app.agents.inventory.proration import (
    ConsumableJobUsage,
    ConsumableLot,
    LotProrationInput,
)

PULL = date(2026, 5, 1)
DEPLETE = date(2026, 5, 30)


def _lot(sku: str, name: str, unit: str, qty: float, cost_cents: int) -> ConsumableLot:
    return ConsumableLot(sku, name, unit, qty, cost_cents, PULL, DEPLETE)


# --------------------------------------------------------------------------------------------
# Pure primitives
# --------------------------------------------------------------------------------------------
class TestLargestRemainderAllocation:
    def test_clean_division_no_remainder(self) -> None:
        # $300 over [10,15,25] ft of 50 total -> 6000 / 9000 / 15000, exact.
        assert pr.largest_remainder_allocation(30_000, [10, 15, 25]) == [6_000, 9_000, 15_000]

    def test_remainder_cent_goes_to_largest_fraction(self) -> None:
        # 30001c over [10,15,25]: exact 6000.2 / 9000.3 / 15000.5 -> floors sum 29999... actually
        # 6000+9000+15000 = 30000, remainder 1 -> largest fraction (.5, the 25ft job) absorbs it.
        assert pr.largest_remainder_allocation(30_001, [10, 15, 25]) == [6_000, 9_000, 15_001]

    def test_zero_total_weight_falls_back_to_even(self) -> None:
        # No usable proxy -> even split; last-by-remainder still sums exactly.
        assert sum(pr.largest_remainder_allocation(10_000, [0, 0, 0])) == 10_000

    @given(
        st.integers(min_value=0, max_value=5_000_000),
        st.lists(st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
                 min_size=1, max_size=12),
    )
    def test_parts_sum_exactly_to_total(self, total: int, weights: list[float]) -> None:
        parts = pr.largest_remainder_allocation(total, weights)
        assert sum(parts) == total
        assert all(p >= 0 for p in parts)


class TestEvenAllocation:
    @pytest.mark.parametrize(
        "total, n, expected",
        [
            (30_000, 4, [7_500, 7_500, 7_500, 7_500]),  # $300 / 4 = $75 each (the spec oracle)
            (10_000, 3, [3_333, 3_333, 3_334]),  # remainder cent to the LAST bucket
            (100, 1, [100]),
        ],
    )
    def test_known(self, total: int, n: int, expected: list[int]) -> None:
        assert pr.even_allocation(total, n) == expected

    @given(st.integers(0, 1_000_000), st.integers(1, 50))
    def test_sums_exactly(self, total: int, n: int) -> None:
        assert sum(pr.even_allocation(total, n)) == total


# --------------------------------------------------------------------------------------------
# prorate_lot — the spec oracles
# --------------------------------------------------------------------------------------------
class TestProrateLotEven:
    def test_spool_300_over_four_jobs_even_is_75_each(self) -> None:
        # $300 vent spool, 4 jobs, no proxies -> auto picks EVEN -> $75 each.
        inp = LotProrationInput(
            lot=_lot("SPOOL-50", "Fortiflex Vent Spool 50ft", "ft", 50, 30_000),
            jobs=[ConsumableJobUsage(f"J{i}") for i in range(1, 5)],
        )
        res = pr.prorate_lot(inp)
        assert res.method == pr.METHOD_EVEN
        assert [a.allocated_cost_cents for a in res.allocations] == [7_500, 7_500, 7_500, 7_500]
        assert sum(a.allocated_cost_cents for a in res.allocations) == 30_000

    def test_by_job_count_method_is_even(self) -> None:
        inp = LotProrationInput(
            lot=_lot("SPOOL-50", "Vent Spool", "ft", 50, 30_000),
            jobs=[ConsumableJobUsage("J1"), ConsumableJobUsage("J2"), ConsumableJobUsage("J3")],
            method=pr.METHOD_BY_JOB_COUNT,
        )
        res = pr.prorate_lot(inp)
        assert res.method == pr.METHOD_EVEN
        # 30000 / 3 = 10000 each, exact
        assert [a.allocated_cost_cents for a in res.allocations] == [10_000, 10_000, 10_000]


class TestProrateLotByUsage:
    def test_copper_by_feet_10_15_25_proportional(self) -> None:
        # $300 copper coil, used 10/15/25 ft across 3 jobs -> proportional 60/90/150.
        inp = LotProrationInput(
            lot=_lot("COIL-CU", "Copper Coil 500ft", "ft", 500, 30_000),
            jobs=[
                ConsumableJobUsage("J1", usage_proxy=10),
                ConsumableJobUsage("J2", usage_proxy=15),
                ConsumableJobUsage("J3", usage_proxy=25),
            ],
        )
        res = pr.prorate_lot(inp)
        assert res.method == pr.METHOD_BY_USAGE  # auto, every job has a proxy
        assert [a.allocated_cost_cents for a in res.allocations] == [6_000, 9_000, 15_000]

    def test_remainder_cent_goes_to_largest_share_job(self) -> None:
        # 30001c over 10/15/25 ft -> 6000 / 9000 / 15001 (the 25ft job, largest share, absorbs the cent).
        inp = LotProrationInput(
            lot=_lot("COIL-CU", "Copper Coil", "ft", 500, 30_001),
            jobs=[
                ConsumableJobUsage("J1", usage_proxy=10),
                ConsumableJobUsage("J2", usage_proxy=15),
                ConsumableJobUsage("J3", usage_proxy=25),
            ],
        )
        res = pr.prorate_lot(inp)
        alloc = {a.job_id: a.allocated_cost_cents for a in res.allocations}
        assert alloc == {"J1": 6_000, "J2": 9_000, "J3": 15_001}
        assert sum(alloc.values()) == 30_001

    def test_partial_proxies_fall_back_to_even(self) -> None:
        # Not every job has a proxy -> auto resolves to EVEN (can't trust a partial proxy split).
        inp = LotProrationInput(
            lot=_lot("COIL-CU", "Copper Coil", "ft", 500, 30_000),
            jobs=[
                ConsumableJobUsage("J1", usage_proxy=10),
                ConsumableJobUsage("J2"),  # unknown draw
            ],
        )
        res = pr.prorate_lot(inp)
        assert res.method == pr.METHOD_EVEN
        assert [a.allocated_cost_cents for a in res.allocations] == [15_000, 15_000]


class TestMiscostStory:
    def test_dump_job_and_miscost_corrected(self) -> None:
        # Even $300 / 4 -> each fair share $75. Today the whole $300 dumps on the last job (J4).
        # Over-cost on J4 = 300 - 75 = $225; the other three are collectively undercosted by $225.
        # Total absolute miscost corrected = 2 * 225 = $450 = 45000c.
        inp = LotProrationInput(
            lot=_lot("SPOOL-50", "Vent Spool", "ft", 50, 30_000),
            jobs=[ConsumableJobUsage(f"J{i}") for i in range(1, 5)],
        )
        res = pr.prorate_lot(inp)
        assert res.dump_job_id == "J4"
        assert res.miscost_corrected_cents == 45_000

    def test_single_job_lot_has_no_miscost(self) -> None:
        # One job legitimately bears the whole lot -> nothing to correct.
        inp = LotProrationInput(
            lot=_lot("SPOOL-50", "Vent Spool", "ft", 50, 30_000),
            jobs=[ConsumableJobUsage("J1")],
        )
        res = pr.prorate_lot(inp)
        assert res.miscost_corrected_cents == 0
        assert res.allocations[0].allocated_cost_cents == 30_000

    def test_empty_jobs_raises(self) -> None:
        inp = LotProrationInput(lot=_lot("X", "X", "ft", 1, 100), jobs=[])
        with pytest.raises(ValueError):
            pr.prorate_lot(inp)

    def test_unknown_method_raises(self) -> None:
        inp = LotProrationInput(
            lot=_lot("X", "X", "ft", 1, 100), jobs=[ConsumableJobUsage("J1")], method="bogus"
        )
        with pytest.raises(ValueError):
            pr.prorate_lot(inp)


# --------------------------------------------------------------------------------------------
# analyze_consumables — the Canyon Ridge fixture scenario
# --------------------------------------------------------------------------------------------
def _scenario() -> list[LotProrationInput]:
    """Canyon Ridge consumables: a 50ft Fortiflex vent spool (even, 4 jobs) and a copper coil
    (by-feet 10/15/25). Hand-computed totals below."""
    spool = LotProrationInput(
        lot=_lot("SPOOL-50", "Fortiflex Vent Spool 50ft", "ft", 50, 30_000),
        jobs=[ConsumableJobUsage(f"VS{i}") for i in range(1, 5)],
    )
    coil = LotProrationInput(
        lot=_lot("COIL-CU", "Copper Line Set Coil 50ft", "ft", 50, 18_000),
        jobs=[
            ConsumableJobUsage("CC1", usage_proxy=10),
            ConsumableJobUsage("CC2", usage_proxy=15),
            ConsumableJobUsage("CC3", usage_proxy=25),
        ],
    )
    return [spool, coil]


class TestAnalyzeConsumables:
    def test_totals(self) -> None:
        res = pr.analyze_consumables(_scenario(), as_of=date(2026, 6, 1))
        # prorated = the two lot costs: 30000 + 18000 = 48000
        assert res.total_prorated_cents == 48_000
        # spool miscost = 2*(30000 - 7500) = 45000; coil dump = CC3 -> 25/50*18000 = 9000,
        # miscost = 2*(18000 - 9000) = 18000. total = 63000.
        assert res.total_miscost_corrected_cents == 63_000

    def test_sorted_by_miscost_desc(self) -> None:
        res = pr.analyze_consumables(_scenario(), as_of=date(2026, 6, 1))
        assert [l.sku for l in res.lots] == ["SPOOL-50", "COIL-CU"]

    def test_coil_split_by_feet(self) -> None:
        res = pr.analyze_consumables(_scenario(), as_of=date(2026, 6, 1))
        coil = next(l for l in res.lots if l.sku == "COIL-CU")
        # 18000 over 10/15/25 of 50 ft -> 3600 / 5400 / 9000
        assert [a.allocated_cost_cents for a in coil.allocations] == [3_600, 5_400, 9_000]

    def test_inputs_hash_stable_and_hex(self) -> None:
        h1 = pr.analyze_consumables(_scenario(), as_of=date(2026, 6, 1)).inputs_hash
        h2 = pr.analyze_consumables(_scenario(), as_of=date(2026, 6, 1)).inputs_hash
        assert h1 == h2
        assert len(h1) == 64 and all(c in "0123456789abcdef" for c in h1)


class TestFixtureClientAssembly:
    """The Canyon Ridge fixture lots flow through the real fixture client + engine + schema mapper."""

    async def test_fixture_lots_prorate_and_map_to_usd(self) -> None:
        from datetime import datetime, timezone

        from app.agents.inventory.schemas import build_proration_result
        from app.integrations.inventory.fixture_client import FixtureInventoryClient

        lots = await FixtureInventoryClient().get_consumable_lots()
        assert [inp.lot.sku for inp in lots] == ["SPOOL-FX50", "COIL-CU38"]

        analysis = pr.analyze_consumables(lots, as_of=date(2026, 6, 1))
        result = build_proration_result(
            analysis, narrative="x", analysis_timestamp=datetime.now(timezone.utc)
        )
        # Spool: $300 / 4 even -> $75 each at the USD boundary.
        spool = next(l for l in result.lots if l.sku == "SPOOL-FX50")
        assert spool.method == "even"
        assert [a.allocated_cost_usd for a in spool.allocations] == [75.0, 75.0, 75.0, 75.0]
        # Coil: $180 over 10/15/25 ft -> $36 / $54 / $90.
        coil = next(l for l in result.lots if l.sku == "COIL-CU38")
        assert coil.method == "by_usage_proxy"
        assert [a.allocated_cost_usd for a in coil.allocations] == [36.0, 54.0, 90.0]
        # Totals at the boundary: prorated 300+180 = 480; miscost 2*(300-75)+2*(180-90)=450+180=630.
        assert result.totals.total_prorated_usd == 480.0
        assert result.totals.total_miscost_corrected_usd == 630.0


# --------------------------------------------------------------------------------------------
# Consumable → basis catalog (proration_catalog)
# --------------------------------------------------------------------------------------------
from app.agents.inventory import proration_catalog as cat  # noqa: E402


class TestClassifyConsumable:
    @pytest.mark.parametrize(
        "name, sku, unit, expected",
        [
            # LINEAR — drawn by the foot.
            ("Copper Line Set Coil 50ft", "COIL-CU38", "ft", cat.CATEGORY_LINEAR),
            ("Refrigerant Pipe 3/8", "PIPE-38", "ft", cat.CATEGORY_LINEAR),
            ("Fortiflex Vent Spool 50ft", "SPOOL-50", "ft", cat.CATEGORY_LINEAR),
            ("Flexible Duct R8", "DUCT-R8", "ft", cat.CATEGORY_LINEAR),
            ("14AWG THHN Wire", "WIRE-14", "ft", cat.CATEGORY_LINEAR),
            # WEIGHT — drawn by the pound.
            ("R-410A Refrigerant Charge", "REF-410A", "lb", cat.CATEGORY_WEIGHT),
            ("Silver Solder", "SOLDER-AG", "lb", cat.CATEGORY_WEIGHT),
            # DISCRETE — handful per job.
            ("Brass Fitting 1/2", "FIT-12", "ea", cat.CATEGORY_DISCRETE),
            ("Sheet Metal Screws", "SCREW-8", "ea", cat.CATEGORY_DISCRETE),
            ("Duct Sealant Mastic", "SEAL-MAS", "ea", cat.CATEGORY_DISCRETE),
            ("Foil Tape", "TAPE-FOIL", "ea", cat.CATEGORY_DISCRETE),
            ("Pleated Air Filter 16x25", "FILT-1625", "ea", cat.CATEGORY_DISCRETE),
            ("Condensate Whip Kit", "WHIP-K", "ea", cat.CATEGORY_DISCRETE),
        ],
    )
    def test_each_category(self, name: str, sku: str, unit: str, expected: str) -> None:
        assert cat.classify_consumable(name, sku, unit) == expected

    def test_weight_keyword_beats_linear_unit(self) -> None:
        # A "Refrigerant Charge" priced per pound is WEIGHT even though "refrigerant" co-occurs with pipe.
        assert cat.classify_consumable("Refrigerant Charge", "CHG", "lb") == cat.CATEGORY_WEIGHT

    def test_unit_decides_when_no_keyword(self) -> None:
        # No decisive name keyword -> trust the unit of measure.
        assert cat.classify_consumable("Mystery Bulk Roll", "MYS", "ft") == cat.CATEGORY_LINEAR
        assert cat.classify_consumable("Mystery Bulk", "MYS", "lb") == cat.CATEGORY_WEIGHT
        assert cat.classify_consumable("Mystery Widget", "MYS", "ea") == cat.CATEGORY_DISCRETE

    def test_basis_catalog_maps_each_category(self) -> None:
        assert cat.CONSUMABLE_BASIS[cat.CATEGORY_LINEAR] == pr.METHOD_BY_USAGE
        assert cat.CONSUMABLE_BASIS[cat.CATEGORY_WEIGHT] == pr.METHOD_BY_USAGE
        assert cat.CONSUMABLE_BASIS[cat.CATEGORY_DISCRETE] == pr.METHOD_BY_JOB_COUNT

    def test_recommended_basis_uses_explicit_category(self) -> None:
        # An explicit category overrides what the name/unit would classify to.
        assert (
            cat.recommended_basis("Mystery Widget", "MYS", "ea", category=cat.CATEGORY_LINEAR)
            == pr.METHOD_BY_USAGE
        )
        # An invalid explicit category is ignored -> falls back to classification (ea -> discrete).
        assert (
            cat.recommended_basis("Mystery Widget", "MYS", "ea", category="bogus")
            == pr.METHOD_BY_JOB_COUNT
        )


class TestAutoConsultsCatalogOnFallback:
    def test_linear_lot_no_proxies_falls_back_to_even_and_names_basis(self) -> None:
        # A copper line set (LINEAR) with NO usage proxies: auto can't proxy -> EVEN, full allocation,
        # AND the reasoning must name the recommended by_usage_proxy basis + the data to capture.
        inp = LotProrationInput(
            lot=_lot("COIL-CU38", "Copper Line Set Coil 50ft", "ft", 50, 18_000),
            jobs=[ConsumableJobUsage(f"J{i}") for i in range(1, 4)],
        )
        res = pr.prorate_lot(inp)
        assert res.method == pr.METHOD_EVEN
        # 18000 / 3 = 6000 each, exact, sums to the lot.
        assert [a.allocated_cost_cents for a in res.allocations] == [6_000, 6_000, 6_000]
        assert sum(a.allocated_cost_cents for a in res.allocations) == 18_000
        assert "by_usage_proxy" in res.reasoning
        assert "linear feet" in res.reasoning
        assert "linear material" in res.reasoning

    def test_weight_lot_no_proxies_names_pounds_basis(self) -> None:
        inp = LotProrationInput(
            lot=_lot("REF-410A", "R-410A Refrigerant Charge", "lb", 25, 20_000),
            jobs=[ConsumableJobUsage("J1"), ConsumableJobUsage("J2")],
        )
        res = pr.prorate_lot(inp)
        assert res.method == pr.METHOD_EVEN
        assert "pounds used" in res.reasoning
        assert "weight material" in res.reasoning

    def test_discrete_lot_routes_to_by_job_count_with_no_data_note(self) -> None:
        # Fittings (DISCRETE): per-job IS the right basis -> even split, NO "capture data" note.
        inp = LotProrationInput(
            lot=_lot("FIT-12", "Brass Fitting 1/2", "ea", 100, 12_000),
            jobs=[ConsumableJobUsage(f"J{i}") for i in range(1, 5)],
        )
        res = pr.prorate_lot(inp)
        assert res.method == pr.METHOD_EVEN  # by_job_count is an even split by definition
        assert cat.recommended_basis(inp.lot.name, inp.lot.sku, inp.lot.unit) == pr.METHOD_BY_JOB_COUNT
        assert [a.allocated_cost_cents for a in res.allocations] == [3_000, 3_000, 3_000, 3_000]
        assert "Recommended basis" not in res.reasoning

    def test_explicit_category_overrides_classification_in_reasoning(self) -> None:
        # An "ea"/discrete-by-name lot tagged LINEAR -> auto fallback flags linear-feet capture.
        inp = LotProrationInput(
            lot=ConsumableLot("MYS", "Mystery Widget", "ea", 10, 9_000, PULL, DEPLETE,
                              category=cat.CATEGORY_LINEAR),
            jobs=[ConsumableJobUsage("J1"), ConsumableJobUsage("J2"), ConsumableJobUsage("J3")],
        )
        res = pr.prorate_lot(inp)
        assert res.method == pr.METHOD_EVEN
        assert "linear feet" in res.reasoning

    def test_explicit_even_request_does_not_add_catalog_note(self) -> None:
        # A deliberate even/by_job_count choice is the caller's, not a data gap -> no catalog note even
        # for a linear material.
        inp = LotProrationInput(
            lot=_lot("COIL-CU38", "Copper Line Set Coil 50ft", "ft", 50, 18_000),
            jobs=[ConsumableJobUsage("J1"), ConsumableJobUsage("J2")],
            method=pr.METHOD_EVEN,
        )
        res = pr.prorate_lot(inp)
        assert "Recommended basis" not in res.reasoning

    def test_auto_with_full_proxies_still_picks_by_usage_no_note(self) -> None:
        # Regression guard: a linear lot WITH proxies must still resolve by_usage and carry no note.
        inp = LotProrationInput(
            lot=_lot("COIL-CU38", "Copper Line Set Coil 50ft", "ft", 50, 18_000),
            jobs=[
                ConsumableJobUsage("J1", usage_proxy=10),
                ConsumableJobUsage("J2", usage_proxy=15),
                ConsumableJobUsage("J3", usage_proxy=25),
            ],
        )
        res = pr.prorate_lot(inp)
        assert res.method == pr.METHOD_BY_USAGE
        assert [a.allocated_cost_cents for a in res.allocations] == [3_600, 5_400, 9_000]
        assert "Recommended basis" not in res.reasoning

    def test_category_included_in_inputs_hash(self) -> None:
        # The appended category field must change the deterministic hash when set.
        base = LotProrationInput(
            lot=_lot("COIL-CU38", "Copper Line Set Coil 50ft", "ft", 50, 18_000),
            jobs=[ConsumableJobUsage("J1"), ConsumableJobUsage("J2")],
        )
        tagged = LotProrationInput(
            lot=ConsumableLot("COIL-CU38", "Copper Line Set Coil 50ft", "ft", 50, 18_000, PULL,
                              DEPLETE, category=cat.CATEGORY_WEIGHT),
            jobs=[ConsumableJobUsage("J1"), ConsumableJobUsage("J2")],
        )
        assert pr.prorate_lot(base).inputs_hash != pr.prorate_lot(tagged).inputs_hash


class TestAllocationSumProperty:
    @given(
        st.integers(min_value=1, max_value=2_000_000),
        st.lists(st.floats(min_value=0.1, max_value=500, allow_nan=False, allow_infinity=False),
                 min_size=1, max_size=10),
    )
    def test_by_usage_allocations_always_sum_to_lot_cost(self, cost: int, proxies: list[float]) -> None:
        inp = LotProrationInput(
            lot=_lot("X", "X", "ft", sum(proxies), cost),
            jobs=[ConsumableJobUsage(f"J{i}", usage_proxy=p) for i, p in enumerate(proxies)],
        )
        res = pr.prorate_lot(inp)
        assert sum(a.allocated_cost_cents for a in res.allocations) == cost
