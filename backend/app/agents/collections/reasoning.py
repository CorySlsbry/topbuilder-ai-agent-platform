"""Reasoning (narration) layer for the Collections agent. Numbers in, prose out — never computes."""
from __future__ import annotations

import json

from app.agents._narrate import narrate
from app.agents.collections.analytics import (
    STATUS_EXPECTING_MONEY,
    STATUS_RECONCILED,
    STATUS_STALLED_OTHER_COURT,
    CollectionsAnalysis,
)
from app.agents.collections.prompts import SYSTEM_PERSONA
from app.config import Settings


def _usd(cents: int) -> float:
    return round(cents / 100, 2)


def _analysis_brief(analysis: CollectionsAnalysis) -> dict:
    t = analysis.totals
    return {
        "as_of": analysis.as_of.isoformat(),
        "totals": {
            "customers": t.customers,
            "open_balance_usd": _usd(t.open_balance_cents),
            "overdue_balance_usd": _usd(t.overdue_balance_cents),
            "current_balance_usd": _usd(t.current_balance_cents),
            "pct_current": t.pct_current,
            "pct_over_30": t.pct_over_30,
            "at_risk_balance_usd": _usd(t.at_risk_balance_cents),
            "customers_needing_action": t.customers_needing_action,
            "bucket_balances_usd": {k: _usd(v) for k, v in t.bucket_balances_cents.items()},
        },
        "worklist": [
            {
                "customer": c.customer_name,
                "balance_usd": _usd(c.balance_cents),
                "days_overdue": c.oldest_days_overdue,
                "bucket": c.bucket,
                "status": c.status,
                "owner": c.owner,
                "dunning_step": c.dunning_step,
                "dunning_channel": c.dunning_channel,
                "promise_date": c.promise_date.isoformat() if c.promise_date else None,
                "promise_amount_usd": _usd(c.promise_amount_cents) if c.promise_amount_cents else None,
                "next_action": c.next_action,
            }
            for c in analysis.worklist
        ],
    }


def _template_narrative(analysis: CollectionsAnalysis) -> str:
    t = analysis.totals
    if t.customers == 0:
        return "No open A/R in this batch. Nothing to collect."

    overdue = _usd(t.overdue_balance_cents)
    at_risk = _usd(t.at_risk_balance_cents)
    lines = [
        f"Across {t.customers} customer(s) with ${_usd(t.open_balance_cents):,.0f} of open A/R, "
        f"${overdue:,.0f} is past due ({t.pct_over_30:.0f}% over 30 days, only "
        f"{t.pct_current:.0f}% current). ${at_risk:,.0f} sits in the 91+ buckets — a reserve / "
        f"write-off candidate. {t.customers_needing_action} account(s) need outbound dunning now.",
        "",
    ]

    actionable = [
        c for c in analysis.worklist
        if c.status not in (STATUS_RECONCILED, STATUS_EXPECTING_MONEY, STATUS_STALLED_OTHER_COURT)
    ]
    for c in actionable[:4]:
        lines.append(
            f"- {c.customer_name}: ${_usd(c.balance_cents):,.0f}, {c.oldest_days_overdue}d overdue "
            f"({c.bucket}). {c.next_action} [owner: {c.owner}]"
        )

    promised = [c for c in analysis.worklist if c.status == STATUS_EXPECTING_MONEY]
    if promised:
        names = ", ".join(c.customer_name for c in promised)
        lines.append(f"- Expecting money (promise-to-pay on file): {names} — confirm receipt by the date.")

    disputed = [c for c in analysis.worklist if c.status == STATUS_STALLED_OTHER_COURT]
    if disputed:
        names = ", ".join(c.customer_name for c in disputed)
        lines.append(f"- Disputed (route to account manager): {names}.")

    if actionable:
        top = actionable[0]
        lines.append("")
        lines.append(
            f"Recommended action: work {top.customer_name} first (oldest at "
            f"{top.oldest_days_overdue}d, ${_usd(top.balance_cents):,.0f}), then down the age-sorted list."
        )
    return "\n".join(lines)


def _adapt_provider(text: str, provider: str) -> str:
    """Narration-only provider adaptation (ADR 0003 — figures untouched)."""
    if provider and provider not in ("QuickBooks", "ServiceTitan") and "QuickBooks" in text:
        text = text.replace("QuickBooks", provider)
    return text


async def explain(
    analysis: CollectionsAnalysis,
    settings: Settings,
    lessons: str = "",
    provider: str = "QuickBooks",
) -> str:
    # `lessons` = retrieved self-learning memory (past wins/edits). It steers the NARRATION only;
    # the persona forbids recomputing any figure, so the numbers stay deterministic.
    brief = _analysis_brief(analysis)
    template = _adapt_provider(_template_narrative(analysis), provider)
    user_content = (
        "Authoritative analysis (quote, do not recompute):\n```json\n"
        + json.dumps(brief, indent=2)
        + "\n```"
        + (
            "\n\nLessons from past human feedback on this agent — apply where "
            "relevant, but STILL quote every figure above exactly:\n" + lessons
            if lessons
            else ""
        )
        + "\nWrite the executive narrative."
    )
    narrative = await narrate(
        agent="collections",
        settings=settings,
        system=[{"type": "text", "text": SYSTEM_PERSONA, "cache_control": {"type": "ephemeral"}}],
        user_content=user_content,
        brief=brief,
        template=template,
    )
    return _adapt_provider(narrative, provider)
