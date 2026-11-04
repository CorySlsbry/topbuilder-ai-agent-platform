"""Deterministic generator for the ServiceTitan demo fixtures.

Run from backend/:  python scripts/generate_fixtures.py

Produces the JSON the FixtureServiceTitanClient reads. Appointment/timesheet dates are stored as
*day offsets* from `as_of` so the demo is always forward-looking. The scenario is hand-designed to
be board-room legible:

  • HVAC summer spike -> escalating understaffing (week 1: ~1 tech short, week 2: ~2 techs short)
  • Two senior HVAC techs pushed into avoidable overtime in weeks 1-2
  • Electrical underutilized (demand < capacity) -> redistribution narrative
  • Plumbing / install steady (control trades)

Everything is deterministic (no RNG) so regenerating yields identical files.
"""
from __future__ import annotations

import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parents[1] / "app" / "integrations" / "servicetitan" / "fixtures"

# --- reference data ---------------------------------------------------------------------------
TECHNICIANS = [
    {"id": "t-h1", "name": "Alice Nguyen",   "trade": "hvac",       "contracted_weekly_hours": 40, "hourly_cost": 48, "overtime_multiplier": 1.5, "active": True},
    {"id": "t-h2", "name": "Ben Carter",     "trade": "hvac",       "contracted_weekly_hours": 40, "hourly_cost": 48, "overtime_multiplier": 1.5, "active": True},
    {"id": "t-h3", "name": "Carlos Ortega",  "trade": "hvac",       "contracted_weekly_hours": 40, "hourly_cost": 46, "overtime_multiplier": 1.5, "active": True},
    {"id": "t-h4", "name": "Dana Whitfield", "trade": "hvac",       "contracted_weekly_hours": 40, "hourly_cost": 46, "overtime_multiplier": 1.5, "active": True},
    {"id": "t-p1", "name": "Eve Robinson",   "trade": "plumbing",   "contracted_weekly_hours": 40, "hourly_cost": 47, "overtime_multiplier": 1.5, "active": True},
    {"id": "t-p2", "name": "Frank Dubois",   "trade": "plumbing",   "contracted_weekly_hours": 40, "hourly_cost": 47, "overtime_multiplier": 1.5, "active": True},
    {"id": "t-e1", "name": "Grace Lee",      "trade": "electrical", "contracted_weekly_hours": 40, "hourly_cost": 50, "overtime_multiplier": 1.5, "active": True},
    {"id": "t-e2", "name": "Henry Park",     "trade": "electrical", "contracted_weekly_hours": 40, "hourly_cost": 50, "overtime_multiplier": 1.5, "active": True},
    {"id": "t-e3", "name": "Ivan Petrov",    "trade": "electrical", "contracted_weekly_hours": 40, "hourly_cost": 49, "overtime_multiplier": 1.5, "active": True},
    {"id": "t-g1", "name": "Jack Moreno",    "trade": "install",    "contracted_weekly_hours": 40, "hourly_cost": 44, "overtime_multiplier": 1.5, "active": True},
]

TRADE_ECONOMICS = [
    {"trade": "hvac",       "billable_rate": 145, "availability_factor": 0.85},
    {"trade": "plumbing",   "billable_rate": 140, "availability_factor": 0.85},
    {"trade": "electrical", "billable_rate": 150, "availability_factor": 0.85},
    {"trade": "install",    "billable_rate": 120, "availability_factor": 0.85},
]

JOB_DURATIONS = [
    {"job_type": "maintenance_tuneup",  "trade": "hvac",       "mean_hours": 1.5, "stddev_hours": 0.4, "sample_size": 540, "completion_rate": 0.99},
    {"job_type": "ac_repair",           "trade": "hvac",       "mean_hours": 2.5, "stddev_hours": 0.8, "sample_size": 320, "completion_rate": 0.86},
    {"job_type": "furnace_repair",      "trade": "hvac",       "mean_hours": 2.8, "stddev_hours": 0.9, "sample_size": 210, "completion_rate": 0.84},
    {"job_type": "ac_install",          "trade": "hvac",       "mean_hours": 8.0, "stddev_hours": 1.5, "sample_size": 140, "completion_rate": 0.95},
    {"job_type": "drain_clear",         "trade": "plumbing",   "mean_hours": 1.8, "stddev_hours": 0.6, "sample_size": 260, "completion_rate": 0.90},
    {"job_type": "water_heater_install","trade": "plumbing",   "mean_hours": 4.5, "stddev_hours": 1.0, "sample_size": 95,  "completion_rate": 0.94},
    {"job_type": "outlet_service",      "trade": "electrical", "mean_hours": 1.2, "stddev_hours": 0.4, "sample_size": 300, "completion_rate": 0.97},
    {"job_type": "panel_upgrade",       "trade": "electrical", "mean_hours": 6.0, "stddev_hours": 1.2, "sample_size": 70,  "completion_rate": 0.93},
    {"job_type": "ductwork",            "trade": "install",    "mean_hours": 7.0, "stddev_hours": 2.0, "sample_size": 60,  "completion_rate": 0.90},
]

DEMAND_INDEX = [
    {"trade": "hvac",       "week_offset": 0, "demand_index": 1.15},
    {"trade": "hvac",       "week_offset": 1, "demand_index": 1.30},
    {"trade": "hvac",       "week_offset": 2, "demand_index": 1.45},
    {"trade": "plumbing",   "week_offset": 0, "demand_index": 1.00},
    {"trade": "plumbing",   "week_offset": 1, "demand_index": 1.05},
    {"trade": "plumbing",   "week_offset": 2, "demand_index": 1.05},
    {"trade": "electrical", "week_offset": 0, "demand_index": 0.90},
    {"trade": "electrical", "week_offset": 1, "demand_index": 0.90},
    {"trade": "electrical", "week_offset": 2, "demand_index": 0.85},
    {"trade": "install",    "week_offset": 0, "demand_index": 1.00},
    {"trade": "install",    "week_offset": 1, "demand_index": 1.00},
    {"trade": "install",    "week_offset": 2, "demand_index": 1.00},
]

# Per-(technician, week) assigned billable hours. This is the lever that creates the story.
ASSIGNED_HOURS = {
    # HVAC — escalating load; Alice & Ben tip into overtime in weeks 1-2
    "t-h1": [28, 42, 46], "t-h2": [26, 26, 44], "t-h3": [26, 24, 22], "t-h4": [24, 24, 20],
    # Plumbing — steady, no OT, no gap
    "t-p1": [30, 30, 31], "t-p2": [28, 30, 29],
    # Electrical — underutilized (redistribution candidates / overstaffing signal)
    "t-e1": [22, 20, 18], "t-e2": [20, 20, 16], "t-e3": [18, 16, 16],
    # Install — steady control
    "t-g1": [30, 28, 26],
}

# Job menus per trade for splitting a weekly hour-target into realistic appointments.
JOB_MENU = {
    "hvac":       [(1.5, "maintenance_tuneup"), (2.5, "ac_repair"), (2.8, "furnace_repair"), (8.0, "ac_install")],
    "plumbing":   [(1.8, "drain_clear"), (4.5, "water_heater_install"), (1.8, "drain_clear")],
    "electrical": [(1.2, "outlet_service"), (6.0, "panel_upgrade"), (1.2, "outlet_service")],
    "install":    [(7.0, "ductwork"), (3.5, "ductwork")],
}

TRADE_BY_TECH = {t["id"]: t["trade"] for t in TECHNICIANS}


def split_into_jobs(target: float, menu: list[tuple[float, str]], rotate: int) -> list[tuple[float, str]]:
    """Deterministically split `target` hours into menu-sized jobs that sum exactly to target."""
    jobs: list[tuple[float, str]] = []
    acc = 0.0
    i = rotate
    guard = 0
    while target - acc >= 0.5 and guard < 100:
        hours, jtype = menu[i % len(menu)]
        if acc + hours <= target + 1e-9:
            jobs.append((hours, jtype))
            acc += hours
        i += 1
        guard += 1
        if all(acc + h > target + 1e-9 for h, _ in menu):
            break
    remainder = round(target - acc, 2)
    if remainder >= 0.5:
        jobs.append((remainder, menu[0][1]))
    return jobs


def build_appointments() -> list[dict]:
    appts: list[dict] = []
    seq = 0
    for tech_id, weekly in ASSIGNED_HOURS.items():
        trade = TRADE_BY_TECH[tech_id]
        menu = JOB_MENU[trade]
        for week, target in enumerate(weekly):
            jobs = split_into_jobs(float(target), menu, rotate=week + len(tech_id))
            for k, (hours, jtype) in enumerate(jobs):
                day_offset = week * 7 + 1 + (k % 5)  # Mon–Fri of that week
                seq += 1
                appts.append(
                    {
                        "id": f"appt-{seq:04d}",
                        "job_id": f"job-{seq:04d}",
                        "trade": trade,
                        "day_offset": day_offset,
                        "scheduled_hours": round(hours, 2),
                        "job_type": jtype,
                        "technician_id": tech_id,
                        "status": "scheduled",
                    }
                )
    return appts


def build_timesheets() -> list[dict]:
    """Two weeks of history; Alice/Ben already trending into OT (context for the narrative)."""
    recent_ot = {"t-h1": [2.0, 3.0], "t-h2": [1.0, 2.0]}
    rows: list[dict] = []
    for tech in TECHNICIANS:
        for week_back in (2, 1):
            ot = recent_ot.get(tech["id"], [0.0, 0.0])[2 - week_back]
            # one summary row per prior week, placed mid-week
            rows.append(
                {
                    "technician_id": tech["id"],
                    "day_offset": -(week_back * 7) + 3,
                    "regular_hours": 40.0 if ot > 0 else 36.0,
                    "overtime_hours": float(ot),
                }
            )
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "technicians.json": TECHNICIANS,
        "trade_economics.json": TRADE_ECONOMICS,
        "job_durations.json": JOB_DURATIONS,
        "demand_index.json": DEMAND_INDEX,
        "appointments.json": build_appointments(),
        "timesheets.json": build_timesheets(),
    }
    for name, data in files.items():
        (OUT / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {name}: {len(data)} rows")


if __name__ == "__main__":
    main()
