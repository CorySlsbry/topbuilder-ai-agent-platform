"""Executive KPI rollup — PURE aggregation over persisted agent run results (no DB, no IO).

ADR 0003 applies end-to-end: every figure here was computed deterministically by an agent engine
and persisted with its run. This layer only sums and relabels those existing fields for the
executive view — it never computes a new business number. Missing runs / missing fields are
defensive: the KPI goes null with detail "No run yet", never an error.
"""
from __future__ import annotations

from app.org.permissions import AGENT_CARDS

# Each agent's owning ("home") department — the first dept_key on its org card. Used to color and
# group every timeseries metric by department for the department-separated dashboards.
_AGENT_HOME_DEPT: dict[str, str] = {
    card["key"]: card["dept_keys"][0] for card in AGENT_CARDS if card["dept_keys"]
}

# (key, label, agent, unit, path into the agent's latest persisted result, detail when present).
# Field paths mirror each agent's schemas.py result shape exactly.
_AGENT_KPIS: tuple[tuple[str, str, str, str, tuple[str, ...], str], ...] = (
    ("booking_recovered", "Booking revenue recovered", "booking", "usd",
     ("totals", "recovered_revenue_usd"),
     "Estimated revenue from intakes the Booking agent qualified and proposed."),
    ("after_hours_captured", "After-hours revenue captured", "booking", "usd",
     ("totals", "after_hours_recovered_usd"),
     "Revenue booked off after-hours calls that would otherwise have been missed."),
    ("drive_time_saved", "Drive time saved", "routing", "minutes_per_day",
     ("totals", "drive_minutes_saved"),
     "Daily drive minutes the Routing agent removed from the dispatch board."),
    ("margin_leakage_flagged", "Margin leakage flagged", "financial", "usd",
     ("totals", "total_leakage_usd"),
     "Leakage the Financial agent flagged across at-risk jobs."),
    ("inventory_savings", "Inventory savings identified", "inventory", "usd",
     ("totals", "total_arbitrage_annual_usd"),
     "Annual vendor-arbitrage savings the Inventory agent found."),
    ("documents_value_extracted", "Document value extracted", "documents", "usd",
     ("totals", "extracted_value_usd"),
     "Dollar amounts the Documents agent extracted and filed."),
    ("technicians_in_overtime", "Technicians trending into overtime", "workforce", "count",
     ("totals", "technicians_in_overtime"),
     "Field technicians the Workforce agent projects into avoidable overtime."),
)

# Additive export for the demo-history seeder (app/org/demo_history.py): the distinct agents whose
# persisted totals power the charted series, in chart order. Derived from _AGENT_KPIS so the seeder
# and the aggregator can never drift apart.
CHARTED_AGENTS: tuple[str, ...] = tuple(
    dict.fromkeys(agent for _, _, agent, _, _, _ in _AGENT_KPIS)
)

# The one $ figure that represents each agent on the value-by-agent chart. Booking's after-hours
# figure is a subset of its recovered revenue, so the chart uses the headline and never re-adds it.
_HEADLINE_USD_KPI: dict[str, str] = {
    "booking": "booking_recovered",
    "financial": "margin_leakage_flagged",
    "inventory": "inventory_savings",
    "documents": "documents_value_extracted",
}


def _field(result: dict | None, path: tuple[str, ...]) -> float | int | None:
    """Walk `path` into a persisted result; anything missing or non-numeric = no figure."""
    node: object = result
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node if isinstance(node, (int, float)) and not isinstance(node, bool) else None


def aggregate_kpis(
    latest: dict[str, dict | None], *, departments: list[dict], employee_count: int
) -> dict:
    """The /v1/org/kpis payload from each agent's latest persisted run result (or None)."""
    agent_rows: list[dict] = []
    usd_total = 0.0
    contributors: list[str] = []
    for key, label, agent, unit, path, detail in _AGENT_KPIS:
        value = _field(latest.get(agent), path)
        agent_rows.append({
            "key": key,
            "label": label,
            "value": value,
            "unit": unit,
            "agent": agent,
            "detail": detail if value is not None else "No run yet",
        })
        if value is not None and unit == "usd":
            usd_total += value
            if agent not in contributors:
                contributors.append(agent)

    total_row = {
        "key": "total_value_identified",
        "label": "Value identified by the agents",
        "value": round(usd_total, 2) if contributors else None,
        "unit": "usd",
        "agent": None,
        "detail": (
            f"From the latest {', '.join(contributors)} runs" if contributors else "No runs yet"
        ),
    }

    agents_with_runs = [card for card in AGENT_CARDS if latest.get(card["key"]) is not None]
    covered_keys = {dept for card in agents_with_runs for dept in card["dept_keys"]}
    departments_covered = sum(1 for d in departments if d.get("key") in covered_keys)

    coverage_row = {
        "key": "ai_coverage",
        "label": "AI department coverage",
        "value": departments_covered,
        "unit": "count",
        "agent": None,
        "detail": f"of {len(departments)} departments served by an active agent",
    }

    rows_by_key = {row["key"]: row for row in agent_rows}
    cards_by_agent = {card["key"]: card for card in AGENT_CARDS}
    value_by_agent = [
        {"agent": agent, "label": cards_by_agent[agent]["label"], "usd": rows_by_key[kpi]["value"]}
        for agent, kpi in _HEADLINE_USD_KPI.items()
        if rows_by_key[kpi]["value"] is not None
    ]

    return {
        "kpis": [total_row, *agent_rows, coverage_row],
        "value_by_agent": value_by_agent,
        "headcount_by_department": [
            {
                "key": d.get("key"),
                "name": d.get("name"),
                "color": d.get("color"),
                "head_count": int(d.get("head_count") or 0),
            }
            for d in departments
        ],
        "agents_active": len(agents_with_runs),
        "runs_present": len(agents_with_runs),
        "employee_count": employee_count,
        "departments_covered": departments_covered,
    }


def _as_iso(value: object) -> str | None:
    """Normalize a run's date (a date/datetime or an ISO string) to a YYYY-MM-DD string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value[:10]
    iso = getattr(value, "isoformat", None)
    return iso()[:10] if callable(iso) else None


def aggregate_kpis_timeseries(
    runs: list[dict],
    departments: list[dict],
    start: object,
    end: object,
    dept_filter: list[str] | None,
) -> dict:
    """Daily KPI history from persisted agent runs — the "go backwards" view (ADR 0003: only reads
    the same persisted `totals.*` figures the snapshot rollup reads; never recomputes a number).

    ``runs`` is a flat list of ``{"date": date|datetime|str, "agent": str, "result": dict|None}``.
    For a given (date, agent) the LAST entry wins (mirrors "latest run of the day"). Returns a date
    axis over [start, end] inclusive plus one series per metric, each tagged with its agent, home
    department, unit, label, color, and a value-or-null point for every date on the axis (a gap day
    is null, never zero). ``dept_filter`` (None/empty = all) keeps only metrics whose home
    department is named — an unknown department yields no series (the chart renders an empty grid).
    """
    start_iso, end_iso = _as_iso(start), _as_iso(end)

    # Date axis: every day a run landed within the window, sorted ascending and de-duplicated.
    dates: list[str] = sorted(
        {
            d
            for r in runs
            if (d := _as_iso(r.get("date"))) is not None
            and (start_iso is None or d >= start_iso)
            and (end_iso is None or d <= end_iso)
        }
    )

    # Latest run result per (date, agent) — later list entries override earlier ones for that key.
    latest_by_day_agent: dict[tuple[str, str], dict | None] = {}
    for r in runs:
        day = _as_iso(r.get("date"))
        if day is None or day not in dates:
            continue
        latest_by_day_agent[(day, r.get("agent"))] = r.get("result")

    color_by_dept = {d.get("key"): d.get("color") for d in departments}
    wanted = set(dept_filter) if dept_filter else None  # None/[] -> all departments

    series: list[dict] = []
    for key, label, agent, unit, path, _detail in _AGENT_KPIS:
        dept = _AGENT_HOME_DEPT.get(agent)
        if wanted is not None and dept not in wanted:
            continue
        points = [
            {"date": day, "value": _field(latest_by_day_agent.get((day, agent)), path)}
            for day in dates
        ]
        series.append({
            "key": key,
            "label": label,
            "agent": agent,
            "department": dept,
            "color": color_by_dept.get(dept),
            "unit": unit,
            "points": points,
        })

    return {"dates": dates, "series": series}
