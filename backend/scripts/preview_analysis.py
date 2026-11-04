"""Preview the Workforce analysis against the fixtures — no DB, no API key required.

Usage (from backend/):  python scripts/preview_analysis.py [--horizon 21] [--as-of 2026-06-01]
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
from datetime import date, datetime, timezone

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.agents.workforce.analytics import analyze  # noqa: E402
from app.agents.workforce.data import assemble_workforce_data  # noqa: E402
from app.agents.workforce.reasoning import explain  # noqa: E402
from app.agents.workforce.schemas import build_result  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.integrations.servicetitan.client import get_servicetitan_client  # noqa: E402


async def main(as_of: date, horizon: int) -> None:
    settings = get_settings()
    client = get_servicetitan_client(as_of=as_of, settings=settings)
    data = await assemble_workforce_data(client, as_of=as_of, horizon_days=horizon)
    analysis = analyze(data)
    narrative = await explain(analysis, settings)
    result = build_result(
        analysis, narrative=narrative, analysis_timestamp=datetime.now(timezone.utc)
    )

    print("=" * 78)
    print(f"WORKFORCE ANALYSIS  |  as_of={result.as_of}  horizon={result.horizon_days}d  "
          f"st_mode={settings.servicetitan_mode}")
    print(f"inputs_hash={result.inputs_hash[:16]}...  appts={len(data.appointments)}  "
          f"techs={len(data.technicians)}")
    print("=" * 78)
    t = result.totals
    print(f"TOTALS: {t.weeks_short} trade-week(s) short  (${t.total_understaffing_impact_usd:,.0f} "
          f"at-risk margin)   |   {t.technicians_in_overtime} tech(s) in OT "
          f"(${t.total_overtime_premium_usd:,.0f} premium)")
    print()

    print("UNDERSTAFFING RISKS")
    if not result.understaffing_risks:
        print("  (none)")
    for r in result.understaffing_risks:
        print(f"  [{r.trade_type:>10}] wk {r.week_start}  gap {r.gap_hours:>5.1f}h "
              f"(~{r.gap_count} tech-wk)  ${r.economic_impact_usd:>8,.0f}  conf {r.confidence:.2f}")
    print()

    print("OVERTIME RISKS")
    if not result.overtime_risks:
        print("  (none)")
    for r in result.overtime_risks:
        print(f"  {r.technician_name:>16} ({r.trade})  OT {r.projected_overtime_hours:>4.1f}h  "
              f"${r.economic_impact_usd:>6,.0f}  conf {r.confidence:.2f}  -> {r.mitigation_strategy}")
    print()

    print("UTILIZATION (projected demand / capacity)")
    for u in result.utilization:
        bar = "#" * min(40, int(u.utilization * 28))
        print(f"  [{u.trade:>10}] wk{u.week_offset}  {u.utilization*100:5.1f}%  {bar}")
    print()

    print("REASONING (narrative)")
    print("-" * 78)
    print(result.reasoning_logs)
    print("-" * 78)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=21)
    parser.add_argument("--as-of", type=str, default=None, help="ISO date; default today")
    args = parser.parse_args()
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    asyncio.run(main(as_of, args.horizon))
