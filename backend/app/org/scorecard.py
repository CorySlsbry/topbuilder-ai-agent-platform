"""Department Scorecard — the PURE, deterministic engine that replaces the manual Bloom Growth L10.

ADR 0003 end-to-end: every figure is produced here by tested, deterministic code; the LLM never
computes one. Calculated KPIs are pure functions of the raw weekly inputs and return ``None`` on a
0/absent denominator (never divide-by-zero, never fabricate). Money is carried internally as integer
**cents** (the ``ScorecardData`` raw figures) and emitted as **dollars** at this engine's boundary
(the ``usd`` KpiValue/EntityRow values + the ``SeriesPoint`` history). No DB, no IO — the data bundle
is assembled separately in ``scorecard_data.py``.

The CATALOG below is the SINGLE source of truth for every KPI across the four departments
(Sales · Operations · Sales + Marketing · Finance). The API serializes it so the frontend selector
knows every KPI; the engine reads it to know which figures are raw vs calculated, their goals, units,
and whether they render per-entity.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# --------------------------------------------------------------------------------------------
# Contract dataclasses (mirror docs/ALEX_SCORECARD_SPEC.md exactly)
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class KpiDef:
    """One KPI definition — the catalog row shared by the engine and the FE selector."""

    key: str
    label: str
    department: str
    unit: str
    calculated: bool
    goal: float | None
    higher_is_better: bool
    description: str


@dataclass(frozen=True)
class SeriesPoint:
    date: str
    value: float | None  # display units (usd dollars, percent, count, hours, ratio, minutes)
    projected: bool = False  # True for forward-projected points (the forecast band), False for actuals


@dataclass(frozen=True)
class KpiValue:
    key: str
    value: float | None
    goal: float | None
    on_goal: bool | None  # higher_is_better ? value>=goal : value<=goal (None if no goal/value)
    delta_pct: float | None  # vs the first present series point
    series: list[SeriesPoint]  # dept-level history


@dataclass(frozen=True)
class EntityRow:
    entity_id: str
    entity_name: str
    role: str  # "sales_rep" | "technician" | "csr"
    values: dict[str, float | None]  # kpi_key -> current value (display units)
    headline_series: list[SeriesPoint]  # small trend for the primary metric


@dataclass(frozen=True)
class DepartmentScorecard:
    key: str
    label: str
    source: str  # "ServiceTitan" | "QuickBooks"
    kpis: list[KpiValue]
    entity_role: str | None  # None for finance
    entity_kpi_keys: list[str]  # which keys render per-entity (side-by-side)
    entities: list[EntityRow]


@dataclass(frozen=True)
class Scorecard:
    period_weeks: int
    departments: list[DepartmentScorecard]
    catalog: list[KpiDef]  # full catalog so the FE selector knows every KPI


# --------------------------------------------------------------------------------------------
# Raw data bundle (assembled in scorecard_data.py from a fixture or a live source)
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RawWeek:
    """One weekly column of raw figures for a department (the ``R`` rows of the catalog).

    ``figures`` maps a *raw* catalog key -> its raw value. Money keys carry integer **cents**;
    everything else carries its natural unit (count, hours, minutes). Calculated keys are NEVER
    stored here — they are derived from these raw figures by the pure helpers below.
    """

    date: str
    figures: dict[str, float | int]


@dataclass(frozen=True)
class RawEntityWeek:
    """One weekly column of a single entity's raw figures (per-rep / per-tech / per-CSR)."""

    date: str
    figures: dict[str, float | int]


@dataclass(frozen=True)
class RawEntity:
    entity_id: str
    entity_name: str
    role: str  # "sales_rep" | "technician" | "csr"
    weeks: list[RawEntityWeek]


@dataclass(frozen=True)
class RawDepartment:
    key: str
    weeks: list[RawWeek]  # chronological weekly columns (oldest -> newest)
    entities: list[RawEntity] = field(default_factory=list)


@dataclass(frozen=True)
class ScorecardData:
    """The full deterministic input: one RawDepartment per scorecard department + shared context."""

    departments: list[RawDepartment]
    business_days_per_week: int = 5
    calls_per_tech_per_day: float = 8.0


# --------------------------------------------------------------------------------------------
# Department metadata (label + source + per-entity config). Keys match the four L10 departments.
# --------------------------------------------------------------------------------------------

_USD_KEYS: frozenset[str] = frozenset(
    {
        # Sales
        "gross_sales",
        "rpl",
        "average_ticket",
        # Operations
        "completed_revenue_service",
        "unbilled_materials",
        "hvac_maint_non_job_rev",
        # Sales + Marketing
        "after_hours_recovered",
        "booking_recovered",
        "avg_booking_value",
        # Finance
        "cash_collected",
        "cash",
        "credit_card_balance",
        "line_of_credit_used",
        "ar_total",
        "ar_current",
        "ar_1_30",
        "ar_31_60",
        "ar_61_90",
        "ar_91_120",
        "ar_121_plus",
        "margin_leakage",
        "average_job_size",
        "department_income",
        "upcoming_jobs_1wk",
        "upcoming_jobs_2wk",
        "upcoming_jobs_4wk",
        "follow_up_backlog",
    }
)


@dataclass(frozen=True)
class _DeptMeta:
    key: str
    label: str
    source: str
    entity_role: str | None
    entity_kpi_keys: tuple[str, ...]
    headline_key: str | None  # the primary metric for an entity's headline trend


_DEPT_META: tuple[_DeptMeta, ...] = (
    _DeptMeta(
        key="sales",
        label="Sales",
        source="ServiceTitan",
        entity_role="sales_rep",
        entity_kpi_keys=(
            "closing_pct",
            "gross_sales",
            "rpl",
            "leads",
            "jobs_sold",
            "opportunities",
            "average_ticket",
            "sold_hours",
            "needs_coaching",
        ),
        headline_key="closing_pct",
    ),
    _DeptMeta(
        key="operations",
        label="Operations",
        source="ServiceTitan",
        entity_role="technician",
        entity_kpi_keys=(
            "utilization",
            "completed_revenue_service",
            "job_count",
            "converted_jobs",
            "conversion_rate",
            "idle_time",
            "driving_time",
            "late_alerts",
            "avg_drive_per_day",
            "avg_idle_per_day",
        ),
        headline_key="utilization",
    ),
    _DeptMeta(
        key="sales_marketing",
        label="Sales + Marketing",
        source="ServiceTitan",
        entity_role="csr",
        entity_kpi_keys=(
            "book_rate",
            "calls_taken",
            "leads_fo",
            "booked",
        ),
        headline_key="book_rate",
    ),
    _DeptMeta(
        key="finance",
        label="Finance",
        source="QuickBooks",
        entity_role=None,
        entity_kpi_keys=(),
        headline_key=None,
    ),
)

_DEPT_LABEL: dict[str, str] = {m.key: m.label for m in _DEPT_META}


# --------------------------------------------------------------------------------------------
# CATALOG — the single source of truth. Every KPI in the spec's four department tables.
# --------------------------------------------------------------------------------------------


def _d(
    key: str,
    label: str,
    department: str,
    unit: str,
    calculated: bool,
    goal: float | None,
    higher_is_better: bool,
    description: str,
) -> KpiDef:
    return KpiDef(key, label, department, unit, calculated, goal, higher_is_better, description)


CATALOG: list[KpiDef] = [
    # --- Sales (ServiceTitan) -----------------------------------------------------------------
    _d("gross_sales", "Gross Sales HVAC", "sales", "usd", False, 145000, True, "Sum of sold revenue."),
    _d("opportunities", "Opportunities", "sales", "count", False, None, True, "Quoted opportunities."),
    _d("jobs_sold", "Jobs Sold", "sales", "count", False, None, True, "Won jobs."),
    _d("closing_pct", "Closing %", "sales", "percent", True, 32, True, "Jobs sold ÷ opportunities × 100."),
    _d("leads", "Leads (week)", "sales", "count", False, 20, True, "Assigned leads this week."),
    _d("rpl", "Revenue per Lead", "sales", "usd", True, 6000, True, "Gross sales ÷ leads."),
    _d("average_ticket", "Average Ticket", "sales", "usd", True, 400, True, "Gross sales ÷ jobs sold."),
    _d("sold_hours", "Sold Hours", "sales", "hours", False, None, True, "Quoted labor hours."),
    _d("tech_generated_leads", "Tech-Generated Leads", "sales", "count", False, None, True,
       "Leads sourced by field technicians."),
    _d("needs_coaching", "Below close-rate target", "sales", "bool", True, None, False,
       "Rep closing % is below the close-rate goal (training flag)."),
    # --- Operations (ServiceTitan: field + dispatch + warehouse) -----------------------------
    _d("completed_revenue_service", "Completed Revenue (Service)", "operations", "usd", False, 9300, True,
       "Completed service revenue."),
    _d("converted_jobs", "Converted Jobs (all svcs)", "operations", "count", False, None, True,
       "Jobs converted across all services."),
    _d("conversion_rate", "Conversion Rate", "operations", "percent", True, None, True,
       "Converted jobs ÷ dispatched × 100."),
    _d("utilization", "Technician Utilization", "operations", "percent", True, None, True,
       "Billable hours ÷ available hours × 100."),
    _d("job_count", "Job Count", "operations", "count", False, None, True, "Jobs completed."),
    _d("idle_time", "Idle Time", "operations", "hours", False, None, False, "Clocked-not-on-job hours."),
    _d("driving_time", "Driving Time", "operations", "hours", False, None, False, "Drive hours."),
    _d("late_alerts", "Late Alerts", "operations", "count", False, None, False, "Late-arrival alerts."),
    _d("avg_drive_per_day", "Avg Drive / Day", "operations", "hours", True, None, False,
       "Driving time ÷ business days."),
    _d("avg_idle_per_day", "Avg Idle / Day", "operations", "hours", True, None, False,
       "Idle time ÷ business days."),
    _d("drive_time_saved", "Drive-time Saved", "operations", "minutes_per_day", False, None, True,
       "Daily drive minutes removed by the Routing agent."),
    _d("technicians_needed", "Technicians Needed", "operations", "count", True, None, True,
       "ceil((calls per week ÷ business days) ÷ calls per tech per day)."),
    _d("overtime_hours", "Overtime Hours", "operations", "hours", False, None, False,
       "Overtime hours from the payroll engine."),
    _d("understaffing_gap", "Understaffing Gap", "operations", "hours", False, None, False,
       "Unmet staffing hours from the Workforce agent."),
    _d("unbilled_materials", "Unbilled Materials", "operations", "usd", False, None, False,
       "Materials consumed but not billed (Inventory agent)."),
    _d("hvac_maint_non_job_rev", "HVAC Maint — Non-Job Rev", "operations", "usd", False, 10000, True,
       "Maintenance non-job revenue."),
    # --- Sales + Marketing (ServiceTitan: front office) --------------------------------------
    _d("calls_taken", "Calls Taken", "sales_marketing", "count", False, None, True,
       "Inbound calls handled."),
    _d("leads_fo", "Leads", "sales_marketing", "count", False, None, True, "Qualified leads."),
    _d("booked", "Booked", "sales_marketing", "count", False, None, True, "Appointments booked."),
    _d("book_rate", "Book Rate", "sales_marketing", "percent", True, 90, True, "Booked ÷ leads × 100."),
    _d("missed_call_rate", "Missed-Call Rate", "sales_marketing", "percent", True, None, False,
       "Missed ÷ (handled + missed) × 100."),
    _d("after_hours_recovered", "After-hours Recovered", "sales_marketing", "usd", False, None, True,
       "After-hours revenue captured (Booking agent)."),
    _d("booking_recovered", "Booking Recovered", "sales_marketing", "usd", False, None, True,
       "Revenue recovered by the Booking agent."),
    _d("avg_booking_value", "Avg Booking Value", "sales_marketing", "usd", True, None, True,
       "Booking recovered ÷ booked."),
    # --- Finance (QuickBooks) — company-level (no per-entity) ---------------------------------
    _d("cash_collected", "Cash Collected", "finance", "usd", False, 100000, True, "Payments received."),
    _d("cash", "Cash", "finance", "usd", False, 0, True, "Bank balance."),
    _d("credit_card_balance", "Credit Card Balance", "finance", "usd", False, 0, False,
       "Credit-card liability — lower is healthier; on-goal only when paid down to $0."),
    _d("line_of_credit_used", "Line of Credit Used", "finance", "usd", False, 0, False,
       "Line of credit drawn — lower is healthier; on-goal only at $0 drawn."),
    _d("quick_ratio", "Quick Ratio", "finance", "ratio", True, 3, True,
       "(Cash + A/R total) ÷ current liabilities."),
    _d("ar_total", "A/R Total", "finance", "usd", False, None, False, "Sum of the aging buckets."),
    _d("ar_current", "A/R Current", "finance", "usd", False, None, True, "Current (not yet due) aging bucket."),
    _d("ar_1_30", "A/R 1–30", "finance", "usd", False, None, False, "Aging bucket 1–30 days."),
    _d("ar_31_60", "A/R 31–60", "finance", "usd", False, None, False, "Aging bucket 31–60 days."),
    _d("ar_61_90", "A/R 61–90", "finance", "usd", False, None, False, "Aging bucket 61–90 days."),
    _d("ar_91_120", "A/R 91–120", "finance", "usd", False, None, False, "Aging bucket 91–120 days."),
    _d("ar_121_plus", "A/R 121+", "finance", "usd", False, None, False, "Aging bucket 121+ days."),
    _d("ar_pct_current", "A/R % Current", "finance", "percent", True, None, True,
       "A/R current ÷ A/R total × 100."),
    _d("ar_pct_over_30", "A/R % Over 30", "finance", "percent", True, None, False,
       "(A/R total − A/R current) ÷ A/R total × 100."),
    _d("margin_leakage", "Margin Leakage", "finance", "usd", False, None, False,
       "Leakage flagged by the Financial agent."),
    _d("average_job_size", "Average Job Size", "finance", "usd", True, None, True,
       "Completed revenue ÷ jobs."),
    _d("department_income", "Department Income", "finance", "usd", False, None, True, "P&L by department."),
    _d("upcoming_jobs_1wk", "Upcoming Jobs 1 wk", "finance", "usd", False, 130000, True,
       "Scheduled pipeline next week."),
    _d("upcoming_jobs_2wk", "Upcoming Jobs 2 wk", "finance", "usd", False, 283000, True,
       "Scheduled pipeline in 2 weeks."),
    _d("upcoming_jobs_4wk", "Upcoming Jobs 4 wk", "finance", "usd", False, 400000, True,
       "Scheduled pipeline in 4 weeks."),
    _d("follow_up_backlog", "Follow-up Backlog (sold est.)", "finance", "usd", False, 900000, True,
       "Sold-estimate backlog."),
]

CATALOG_BY_KEY: dict[str, KpiDef] = {d.key: d for d in CATALOG}
CATALOG_BY_DEPT: dict[str, list[KpiDef]] = {
    m.key: [d for d in CATALOG if d.department == m.key] for m in _DEPT_META
}


# --------------------------------------------------------------------------------------------
# Calculated-KPI helpers — each a PURE function with a hand-computed oracle test. Money inputs
# are CENTS; outputs are DOLLARS for the usd helpers (rpl/average_ticket/avg_booking_value/
# average_job_size), so they can be compared straight to the dollar goals.
# --------------------------------------------------------------------------------------------


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    """numerator/denominator, or None when the denominator is 0/absent (never divide-by-zero)."""
    if not denominator:
        return None
    return numerator / denominator


def closing_pct(jobs_sold: float, opportunities: float) -> float | None:
    """Jobs sold ÷ opportunities × 100 (percent). None when there were no opportunities."""
    ratio = _safe_ratio(jobs_sold, opportunities)
    return None if ratio is None else round(ratio * 100, 2)


def rpl(gross_sales_cents: float, leads: float) -> float | None:
    """Revenue per lead, in DOLLARS. None when there were no leads."""
    ratio = _safe_ratio(gross_sales_cents, leads)
    return None if ratio is None else round(ratio / 100, 2)


def average_ticket(gross_sales_cents: float, jobs_sold: float) -> float | None:
    """Average ticket, in DOLLARS. None when no jobs were sold."""
    ratio = _safe_ratio(gross_sales_cents, jobs_sold)
    return None if ratio is None else round(ratio / 100, 2)


def conversion_rate(converted_jobs: float, dispatched: float) -> float | None:
    """Converted jobs ÷ dispatched × 100 (percent). None when nothing was dispatched."""
    ratio = _safe_ratio(converted_jobs, dispatched)
    return None if ratio is None else round(ratio * 100, 2)


def utilization(billable_hours: float, available_hours: float) -> float | None:
    """Billable hours ÷ available hours × 100 (percent). None when no available hours."""
    ratio = _safe_ratio(billable_hours, available_hours)
    return None if ratio is None else round(ratio * 100, 2)


def avg_per_day(total: float, business_days: float) -> float | None:
    """A weekly total spread across the business days (hours/day). None when no business days."""
    ratio = _safe_ratio(total, business_days)
    return None if ratio is None else round(ratio, 2)


def technicians_needed(
    calls_week: float, business_days: float, calls_per_tech_day: float
) -> int | None:
    """ceil((calls per week ÷ business days) ÷ calls per tech per day). None on a 0 denominator."""
    per_day = _safe_ratio(calls_week, business_days)
    if per_day is None:
        return None
    needed = _safe_ratio(per_day, calls_per_tech_day)
    return None if needed is None else math.ceil(needed)


def book_rate(booked: float, leads_fo: float) -> float | None:
    """Booked ÷ leads × 100 (percent). None when there were no qualified leads."""
    ratio = _safe_ratio(booked, leads_fo)
    return None if ratio is None else round(ratio * 100, 2)


def missed_call_rate(missed: float, handled: float) -> float | None:
    """Missed ÷ (handled + missed) × 100 (percent). None when no calls at all."""
    ratio = _safe_ratio(missed, handled + missed)
    return None if ratio is None else round(ratio * 100, 2)


def avg_booking_value(booking_recovered_cents: float, booked: float) -> float | None:
    """Booking recovered ÷ booked, in DOLLARS. None when nothing was booked."""
    ratio = _safe_ratio(booking_recovered_cents, booked)
    return None if ratio is None else round(ratio / 100, 2)


def quick_ratio(cash_cents: float, ar_total_cents: float, current_liabilities_cents: float) -> float | None:
    """(Cash + A/R) ÷ current liabilities (a dimensionless ratio). None on 0 liabilities."""
    ratio = _safe_ratio(cash_cents + ar_total_cents, current_liabilities_cents)
    return None if ratio is None else round(ratio, 2)


def ar_pct_current(ar_current_cents: float, ar_total_cents: float) -> float | None:
    """A/R current ÷ A/R total × 100 (percent). None when there is no A/R."""
    ratio = _safe_ratio(ar_current_cents, ar_total_cents)
    return None if ratio is None else round(ratio * 100, 2)


def ar_pct_over_30(ar_current_cents: float, ar_total_cents: float) -> float | None:
    """(A/R total − A/R current) ÷ A/R total × 100 (percent). None when there is no A/R."""
    ratio = _safe_ratio(ar_total_cents - ar_current_cents, ar_total_cents)
    return None if ratio is None else round(ratio * 100, 2)


def average_job_size(completed_revenue_cents: float, jobs: float) -> float | None:
    """Completed revenue ÷ jobs, in DOLLARS. None when no jobs."""
    ratio = _safe_ratio(completed_revenue_cents, jobs)
    return None if ratio is None else round(ratio / 100, 2)


def needs_coaching(rep_closing_pct: float | None, goal: float | None) -> bool | None:
    """Rep closing % below the goal (training flag). None when either input is absent."""
    if rep_closing_pct is None or goal is None:
        return None
    return rep_closing_pct < goal


# --------------------------------------------------------------------------------------------
# Display conversion + calculated derivation from a raw-figures dict
# --------------------------------------------------------------------------------------------


def _to_display(key: str, raw_value: float | int | None) -> float | None:
    """Convert a RAW figure to its DISPLAY value: usd cents -> dollars; everything else unchanged."""
    if raw_value is None:
        return None
    if key in _USD_KEYS:
        return round(float(raw_value) / 100, 2)
    return float(raw_value)


def _calc_value(key: str, raw: dict[str, float | int], *, business_days: float, calls_per_tech_day: float) -> float | bool | None:
    """Derive one CALCULATED KPI's DISPLAY value from a raw-figures dict (pure, divide-by-zero-safe).

    Returns None on any 0/absent denominator. `needs_coaching` returns a bool (or None).
    """
    def g(k: str) -> float:
        return float(raw.get(k, 0) or 0)

    if key == "closing_pct":
        return closing_pct(g("jobs_sold"), g("opportunities"))
    if key == "rpl":
        return rpl(g("gross_sales"), g("leads"))
    if key == "average_ticket":
        return average_ticket(g("gross_sales"), g("jobs_sold"))
    if key == "conversion_rate":
        return conversion_rate(g("converted_jobs"), g("dispatched"))
    if key == "utilization":
        return utilization(g("billable_hours"), g("available_hours"))
    if key == "avg_drive_per_day":
        return avg_per_day(g("driving_time"), business_days)
    if key == "avg_idle_per_day":
        return avg_per_day(g("idle_time"), business_days)
    if key == "technicians_needed":
        return technicians_needed(g("calls_week"), business_days, calls_per_tech_day)
    if key == "book_rate":
        return book_rate(g("booked"), g("leads_fo"))
    if key == "missed_call_rate":
        return missed_call_rate(g("missed_calls"), g("calls_taken"))
    if key == "avg_booking_value":
        return avg_booking_value(g("booking_recovered"), g("booked"))
    if key == "quick_ratio":
        return quick_ratio(g("cash"), g("ar_total"), g("current_liabilities"))
    if key == "ar_pct_current":
        return ar_pct_current(g("ar_current"), g("ar_total"))
    if key == "ar_pct_over_30":
        return ar_pct_over_30(g("ar_current"), g("ar_total"))
    if key == "average_job_size":
        return average_job_size(g("completed_revenue_service"), g("jobs_completed"))
    if key == "needs_coaching":
        cp = closing_pct(g("jobs_sold"), g("opportunities"))
        return needs_coaching(cp, CATALOG_BY_KEY["closing_pct"].goal)
    return None


def _value_for(
    kpi: KpiDef, raw: dict[str, float | int], *, business_days: float, calls_per_tech_day: float
) -> float | bool | None:
    """The DISPLAY value of one KPI from a raw-figures dict — calculated or raw."""
    if kpi.calculated:
        return _calc_value(kpi.key, raw, business_days=business_days, calls_per_tech_day=calls_per_tech_day)
    return _to_display(kpi.key, raw.get(kpi.key))


# --------------------------------------------------------------------------------------------
# Goal / delta evaluation
# --------------------------------------------------------------------------------------------


def evaluate_on_goal(value: float | bool | None, goal: float | None, higher_is_better: bool) -> bool | None:
    """on_goal = higher_is_better ? value>=goal : value<=goal. None when no goal or no value."""
    if goal is None or value is None or isinstance(value, bool):
        return None
    return value >= goal if higher_is_better else value <= goal


def delta_pct(series: list[SeriesPoint]) -> float | None:
    """Percent change of the latest present point vs the FIRST present point. None if <2 present
    points, or the first present value is 0 (no meaningful base)."""
    present = [p for p in series if p.value is not None]
    if len(present) < 2:
        return None
    first, last = present[0].value, present[-1].value
    if not first:
        return None
    return round((last - first) / first * 100, 2)  # type: ignore[operator]


# --------------------------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------------------------


def _trim_weeks(weeks: list[RawWeek], n: int) -> list[RawWeek]:
    """The most recent ``n`` weekly columns (chronological order preserved)."""
    return weeks[-n:] if n > 0 else []


def _trim_entity_weeks(weeks: list[RawEntityWeek], n: int) -> list[RawEntityWeek]:
    return weeks[-n:] if n > 0 else []


def _kpi_value(
    kpi: KpiDef, weeks: list[RawWeek], *, business_days: float, calls_per_tech_day: float
) -> KpiValue:
    """A dept-level KpiValue: a history series across the trimmed weeks + current/on_goal/delta."""
    series = [
        SeriesPoint(
            date=w.date,
            value=_as_float_point(
                _value_for(kpi, w.figures, business_days=business_days, calls_per_tech_day=calls_per_tech_day)
            ),
        )
        for w in weeks
    ]
    # The current value is the LAST present point (a gap final week shouldn't read as "no data").
    present = [p.value for p in series if p.value is not None]
    current = present[-1] if present else None
    return KpiValue(
        key=kpi.key,
        value=current,
        goal=kpi.goal,
        on_goal=evaluate_on_goal(current, kpi.goal, kpi.higher_is_better),
        delta_pct=delta_pct(series),
        series=series,
    )


def _as_float_point(value: float | bool | None) -> float | None:
    """Coerce a KPI display value to a series-point float (bool -> 1.0/0.0; None passes through)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    return float(value)


def _entity_row(
    entity: RawEntity,
    entity_kpi_keys: tuple[str, ...],
    headline_key: str | None,
    *,
    business_days: float,
    calls_per_tech_day: float,
) -> EntityRow:
    """A side-by-side entity row: current value per entity_kpi_key + a headline trend."""
    latest = entity.weeks[-1].figures if entity.weeks else {}
    values: dict[str, float | None] = {}
    for key in entity_kpi_keys:
        kpi = CATALOG_BY_KEY[key]
        values[key] = _as_float_point(
            _value_for(kpi, latest, business_days=business_days, calls_per_tech_day=calls_per_tech_day)
        )
    headline_series: list[SeriesPoint] = []
    if headline_key is not None:
        hk = CATALOG_BY_KEY[headline_key]
        headline_series = [
            SeriesPoint(
                date=w.date,
                value=_as_float_point(
                    _value_for(hk, w.figures, business_days=business_days, calls_per_tech_day=calls_per_tech_day)
                ),
            )
            for w in entity.weeks
        ]
    return EntityRow(
        entity_id=entity.entity_id,
        entity_name=entity.entity_name,
        role=entity.role,
        values=values,
        headline_series=headline_series,
    )


def compute_scorecard(data: ScorecardData, *, weeks: int = 13) -> Scorecard:
    """Compute the full department scorecard from the raw weekly bundle (PURE, deterministic).

    Every figure is derived here from the raw inputs (calculated KPIs via the tested helpers above);
    money is emitted in dollars. Each department exposes its dept-level KpiValues (with history) plus
    per-entity rows (reps/techs/CSRs) for the side-by-side panels. ``weeks`` trims to the most recent
    N weekly columns (clamped to >=1).
    """
    n = max(1, weeks)
    raw_by_key = {rd.key: rd for rd in data.departments}
    business_days = float(data.business_days_per_week)
    calls_per_tech_day = float(data.calls_per_tech_per_day)

    departments: list[DepartmentScorecard] = []
    for meta in _DEPT_META:
        rd = raw_by_key.get(meta.key)
        dept_weeks = _trim_weeks(rd.weeks, n) if rd else []
        kpis = [
            _kpi_value(kpi, dept_weeks, business_days=business_days, calls_per_tech_day=calls_per_tech_day)
            for kpi in CATALOG_BY_DEPT[meta.key]
        ]
        entities: list[EntityRow] = []
        if meta.entity_role is not None and rd is not None:
            for ent in rd.entities:
                trimmed = RawEntity(
                    entity_id=ent.entity_id,
                    entity_name=ent.entity_name,
                    role=ent.role,
                    weeks=_trim_entity_weeks(ent.weeks, n),
                )
                entities.append(
                    _entity_row(
                        trimmed,
                        meta.entity_kpi_keys,
                        meta.headline_key,
                        business_days=business_days,
                        calls_per_tech_day=calls_per_tech_day,
                    )
                )
        departments.append(
            DepartmentScorecard(
                key=meta.key,
                label=meta.label,
                source=meta.source,
                kpis=kpis,
                entity_role=meta.entity_role,
                entity_kpi_keys=list(meta.entity_kpi_keys),
                entities=entities,
            )
        )

    return Scorecard(period_weeks=n, departments=departments, catalog=list(CATALOG))


# --------------------------------------------------------------------------------------------
# Serialization (the example-JSON contract the frontend builds to)
# --------------------------------------------------------------------------------------------


def _series_json(series: list[SeriesPoint]) -> list[dict]:
    return [{"date": p.date, "value": p.value, "projected": p.projected} for p in series]


def kpi_def_json(d: KpiDef) -> dict:
    return {
        "key": d.key,
        "label": d.label,
        "department": d.department,
        "unit": d.unit,
        "calculated": d.calculated,
        "goal": d.goal,
        "higher_is_better": d.higher_is_better,
        "description": d.description,
    }


def scorecard_to_json(card: Scorecard) -> dict:
    """Serialize a Scorecard to the spec's example-JSON shape."""
    return {
        "period_weeks": card.period_weeks,
        "catalog": [kpi_def_json(d) for d in card.catalog],
        "departments": [
            {
                "key": dep.key,
                "label": dep.label,
                "source": dep.source,
                "entity_role": dep.entity_role,
                "entity_kpi_keys": dep.entity_kpi_keys,
                "kpis": [
                    {
                        "key": k.key,
                        "value": k.value,
                        "goal": k.goal,
                        "on_goal": k.on_goal,
                        "delta_pct": k.delta_pct,
                        "series": _series_json(k.series),
                    }
                    for k in dep.kpis
                ],
                "entities": [
                    {
                        "entity_id": e.entity_id,
                        "entity_name": e.entity_name,
                        "role": e.role,
                        "values": e.values,
                        "headline_series": _series_json(e.headline_series),
                    }
                    for e in dep.entities
                ],
            }
            for dep in card.departments
        ],
    }
