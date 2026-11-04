"""Oracle tests for the executive KPI rollup (PURE, no DB).

The `latest` dicts below copy the REAL persisted result shapes (the exact field names asserted by
the per-agent fixture oracles, e.g. booking recovered_revenue_usd 3260 / after_hours 2895 in
test_booking_data.py). aggregate_kpis only sums and relabels those existing figures (ADR 0003) —
these tests pin the payload contract the frontend executive view codes against.
"""
from __future__ import annotations

from app.org import permissions
from app.org.kpis import aggregate_kpis

PINNED_KPI_KEYS = [
    "total_value_identified",
    "booking_recovered",
    "after_hours_captured",
    "drive_time_saved",
    "margin_leakage_flagged",
    "inventory_savings",
    "documents_value_extracted",
    "technicians_in_overtime",
    "ai_coverage",
]

BOOKING_RECOVERED_USD = 3260.00
AFTER_HOURS_USD = 2895.00
DRIVE_MINUTES_SAVED = 60
LEAKAGE_USD = 14250.50
INVENTORY_SAVINGS_USD = 1875.25
DOCUMENTS_VALUE_USD = 2920.00
TECHS_IN_OVERTIME = 3

LATEST_ALL: dict[str, dict | None] = {
    "workforce": {
        "agent": "workforce",
        "totals": {
            "weeks_short": 2,
            "total_understaffing_impact_usd": 5400.0,
            "technicians_in_overtime": TECHS_IN_OVERTIME,
            "total_overtime_premium_usd": 1280.0,
        },
    },
    "financial": {
        "agent": "financial",
        "totals": {
            "projects_at_risk": 4,
            "total_leakage_usd": LEAKAGE_USD,
            "cash_30_day": 88_000.0,
            "cash_90_day": 64_000.0,
            "lowest_margin_segment": "service",
        },
    },
    "inventory": {
        "agent": "inventory",
        "totals": {
            "reorders_count": 5,
            "total_stockout_exposure_usd": 7200.0,
            "total_shrinkage_usd": 410.0,
            "total_unbilled_usd": 950.0,
            "total_arbitrage_annual_usd": INVENTORY_SAVINGS_USD,
        },
    },
    "booking": {
        "agent": "booking",
        "totals": {
            "intakes_received": 21,
            "qualified": 14,
            "proposed_bookings": 8,
            "screened_out": 6,
            "after_hours_captured": 7,
            "recovered_revenue_usd": BOOKING_RECOVERED_USD,
            "after_hours_recovered_usd": AFTER_HOURS_USD,
        },
    },
    "routing": {
        "agent": "routing",
        "totals": {
            "jobs": 14,
            "assigned": 12,
            "unassigned": 2,
            "techs_used": 6,
            "drive_minutes_optimized": 18,
            "drive_minutes_baseline": 78,
            "drive_minutes_saved": DRIVE_MINUTES_SAVED,
            "hours_saved": 1.0,
        },
    },
    "documents": {
        "agent": "documents",
        "totals": {
            "documents_processed": 12,
            "auto_filed": 9,
            "needs_signature": 1,
            "needs_human": 2,
            "expiring_soon": 1,
            "extracted_value_usd": DOCUMENTS_VALUE_USD,
        },
    },
}

DEPARTMENTS = [
    {**d, "head_count": hc}
    for d, hc in zip(
        permissions.DEPARTMENTS, [3, 5, 3, 18, 3, 3, 3], strict=True
    )
]

EMPLOYEE_COUNT = 38


def _by_key(payload: dict) -> dict[str, dict]:
    return {row["key"]: row for row in payload["kpis"]}


def test_every_pinned_kpi_key_is_present_in_order():
    payload = aggregate_kpis(LATEST_ALL, departments=DEPARTMENTS, employee_count=EMPLOYEE_COUNT)
    assert [row["key"] for row in payload["kpis"]] == PINNED_KPI_KEYS


def test_total_value_identified_is_the_exact_sum_of_the_usd_kpis():
    payload = aggregate_kpis(LATEST_ALL, departments=DEPARTMENTS, employee_count=EMPLOYEE_COUNT)
    total = _by_key(payload)["total_value_identified"]
    expected = round(
        BOOKING_RECOVERED_USD + AFTER_HOURS_USD + LEAKAGE_USD
        + INVENTORY_SAVINGS_USD + DOCUMENTS_VALUE_USD,
        2,
    )
    assert total["value"] == expected  # 25_200.75
    assert total["unit"] == "usd"
    assert total["agent"] is None
    assert total["label"] == "Value identified by the agents"
    for agent in ("booking", "financial", "inventory", "documents"):
        assert agent in total["detail"]


def test_each_agent_kpi_reads_the_persisted_field_exactly():
    payload = aggregate_kpis(LATEST_ALL, departments=DEPARTMENTS, employee_count=EMPLOYEE_COUNT)
    rows = _by_key(payload)
    assert (rows["booking_recovered"]["value"], rows["booking_recovered"]["unit"]) == (
        BOOKING_RECOVERED_USD, "usd")
    assert (rows["after_hours_captured"]["value"], rows["after_hours_captured"]["unit"]) == (
        AFTER_HOURS_USD, "usd")
    assert (rows["drive_time_saved"]["value"], rows["drive_time_saved"]["unit"]) == (
        DRIVE_MINUTES_SAVED, "minutes_per_day")
    assert (rows["margin_leakage_flagged"]["value"], rows["margin_leakage_flagged"]["unit"]) == (
        LEAKAGE_USD, "usd")
    assert (rows["inventory_savings"]["value"], rows["inventory_savings"]["unit"]) == (
        INVENTORY_SAVINGS_USD, "usd")
    assert (rows["documents_value_extracted"]["value"],
            rows["documents_value_extracted"]["unit"]) == (DOCUMENTS_VALUE_USD, "usd")
    assert (rows["technicians_in_overtime"]["value"],
            rows["technicians_in_overtime"]["unit"],
            rows["technicians_in_overtime"]["agent"]) == (TECHS_IN_OVERTIME, "count", "workforce")


def test_missing_agent_run_yields_null_value_and_no_run_yet_detail():
    latest = {**LATEST_ALL, "financial": None}
    payload = aggregate_kpis(latest, departments=DEPARTMENTS, employee_count=EMPLOYEE_COUNT)
    rows = _by_key(payload)
    assert rows["margin_leakage_flagged"]["value"] is None
    assert rows["margin_leakage_flagged"]["detail"] == "No run yet"
    total = rows["total_value_identified"]
    assert total["value"] == round(
        BOOKING_RECOVERED_USD + AFTER_HOURS_USD + INVENTORY_SAVINGS_USD + DOCUMENTS_VALUE_USD, 2
    )
    assert "financial" not in total["detail"]


def test_malformed_result_is_treated_as_no_run_for_the_kpi():
    latest = {**LATEST_ALL, "documents": {"agent": "documents"}}  # totals missing entirely
    payload = aggregate_kpis(latest, departments=DEPARTMENTS, employee_count=EMPLOYEE_COUNT)
    rows = _by_key(payload)
    assert rows["documents_value_extracted"]["value"] is None
    assert rows["documents_value_extracted"]["detail"] == "No run yet"
    assert "documents" not in {v["agent"] for v in payload["value_by_agent"]}


def test_no_runs_at_all_yields_all_null_agent_kpis():
    latest: dict[str, dict | None] = {a: None for a in LATEST_ALL}
    payload = aggregate_kpis(latest, departments=DEPARTMENTS, employee_count=EMPLOYEE_COUNT)
    rows = _by_key(payload)
    for key in PINNED_KPI_KEYS:
        if key == "ai_coverage":
            assert rows[key]["value"] == 0
        else:
            assert rows[key]["value"] is None, key
            assert rows[key]["detail"] in ("No run yet", "No runs yet")
    assert payload["value_by_agent"] == []
    assert payload["agents_active"] == 0
    assert payload["runs_present"] == 0
    assert payload["departments_covered"] == 0


def test_value_by_agent_lists_only_agents_with_a_present_dollar_figure():
    payload = aggregate_kpis(LATEST_ALL, departments=DEPARTMENTS, employee_count=EMPLOYEE_COUNT)
    by_agent = {v["agent"]: v for v in payload["value_by_agent"]}
    assert set(by_agent) == {"booking", "financial", "inventory", "documents"}
    # Booking is represented by its headline figure (after-hours is a subset — never re-added).
    assert by_agent["booking"]["usd"] == BOOKING_RECOVERED_USD
    assert by_agent["financial"]["usd"] == LEAKAGE_USD
    assert by_agent["inventory"]["usd"] == INVENTORY_SAVINGS_USD
    assert by_agent["documents"]["usd"] == DOCUMENTS_VALUE_USD
    assert by_agent["booking"]["label"] == "Booking Agent"


def test_departments_covered_counts_dept_keys_of_agents_with_runs():
    payload = aggregate_kpis(LATEST_ALL, departments=DEPARTMENTS, employee_count=EMPLOYEE_COUNT)
    assert payload["departments_covered"] == 7  # all 6 agents running covers every department
    routing_only: dict[str, dict | None] = {a: None for a in LATEST_ALL}
    routing_only["routing"] = LATEST_ALL["routing"]
    partial = aggregate_kpis(routing_only, departments=DEPARTMENTS, employee_count=EMPLOYEE_COUNT)
    assert partial["departments_covered"] == 1  # the routing card serves dispatch only
    assert partial["agents_active"] == 1
    assert partial["runs_present"] == 1
    coverage = _by_key(partial)["ai_coverage"]
    assert coverage["value"] == 1
    assert coverage["detail"] == "of 7 departments served by an active agent"


def test_headcount_and_employee_count_pass_through():
    payload = aggregate_kpis(LATEST_ALL, departments=DEPARTMENTS, employee_count=EMPLOYEE_COUNT)
    assert payload["employee_count"] == EMPLOYEE_COUNT
    assert payload["headcount_by_department"] == [
        {"key": d["key"], "name": d["name"], "color": d["color"], "head_count": d["head_count"]}
        for d in DEPARTMENTS
    ]
    assert payload["agents_active"] == 6
    assert payload["runs_present"] == 6
