"""Preview the Financial analysis against the fixtures — no DB, no API key required.

Usage (from backend/):  python scripts/preview_financial.py [--as-of 2026-06-01]
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
from datetime import date, datetime, timezone

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.agents.financial.analytics import analyze  # noqa: E402
from app.agents.financial.data import assemble_financial_data  # noqa: E402
from app.agents.financial.reasoning import explain  # noqa: E402
from app.agents.financial.schemas import build_result  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.integrations.accounting.client import get_accounting_client  # noqa: E402


async def main(as_of: date) -> None:
    settings = get_settings()
    client = get_accounting_client(as_of=as_of, settings=settings)
    data = await assemble_financial_data(client, as_of=as_of)
    analysis = analyze(data)
    narrative = await explain(analysis, settings)
    result = build_result(analysis, narrative=narrative, analysis_timestamp=datetime.now(timezone.utc))

    t = result.totals
    print("=" * 78)
    print(f"FINANCIAL FORECAST  |  as_of={result.as_of}  acct_mode={settings.accounting_mode}")
    print("=" * 78)
    print(f"TOTALS: {t.projects_at_risk} project(s) at risk  (${t.total_leakage_usd:,.0f} leakage)   "
          f"|  cash 30d ${t.cash_30_day:,.0f} -> 90d ${t.cash_90_day:,.0f}   "
          f"|  weakest segment: {t.lowest_margin_segment}")
    print()
    print("CASH FLOW (projected)")
    for b in result.cash_flow_projection:
        print(f"  +{b.horizon_days:>2}d  in ${b.inflows:>10,.0f}  out ${b.outflows:>10,.0f}  "
              f"=> cash ${b.projected_cash:>11,.0f}  conf {b.confidence:.2f}")
    print()
    print("WIP PROFITABILITY (index < 1.0 = eroding)")
    for j in result.wip_profitability:
        flag = "  <-- ERODING" if j.profitability_index < 1.0 else ""
        print(f"  [{j.profitability_index:>4.2f}] {j.name:<26} {j.customer_segment:<11} "
              f"margin {j.margin_to_date*100:5.1f}% (budget {j.budget_margin*100:4.1f}%){flag}")
    print()
    print("LEAKAGE WARNINGS")
    for w in result.leakage_warnings:
        print(f"  {w.name:<26} {w.kind:<14} ${w.severity_usd:>9,.0f}  conf {w.confidence:.2f}")
    print()
    print("REASONING")
    print("-" * 78)
    print(result.reasoning_logs)
    print("-" * 78)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", type=str, default=None)
    args = parser.parse_args()
    asyncio.run(main(date.fromisoformat(args.as_of) if args.as_of else date.today()))
