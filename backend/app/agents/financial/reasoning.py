"""Reasoning (narration) layer for the Financial agent. Numbers in, prose out — never computes."""
from __future__ import annotations

import json

from app.agents._narrate import narrate
from app.agents.financial.analytics import FinancialAnalysis
from app.agents.financial.prompts import SYSTEM_PERSONA
from app.config import Settings


def _analysis_brief(analysis: FinancialAnalysis) -> dict:
    return {
        "as_of": analysis.as_of.isoformat(),
        "starting_cash": analysis.starting_cash,
        "cash_flow": [
            {"horizon_days": b.horizon_days, "projected_cash": b.projected_cash, "confidence": b.confidence}
            for b in analysis.cash_flow
        ],
        "leakage": [
            {"job": w.name, "kind": w.kind, "exposure_usd": round(w.severity_cents / 100, 2)}
            for w in analysis.leakage
        ],
        "lowest_margin_segment": (
            min(analysis.segment_margins, key=lambda s: s.margin).segment
            if analysis.segment_margins
            else None
        ),
        "eroding_projects": [
            {"job": j.name, "index": j.profitability_index, "margin": j.margin_to_date}
            for j in analysis.job_profitability
            if j.profitability_index < 1.0
        ],
    }


def _template_narrative(analysis: FinancialAnalysis) -> str:
    cash = {b.horizon_days: b.projected_cash for b in analysis.cash_flow}
    total_leakage = sum(w.severity_cents for w in analysis.leakage) / 100
    if not analysis.leakage:
        base = "Margins are on target across all active projects."
    else:
        base = (
            f"{len(analysis.leakage)} project(s) show margin leakage totaling ~${total_leakage:,.0f}."
        )
    lines = [
        f"Cash is projected to move from ${analysis.starting_cash:,.0f} today to "
        f"${cash.get(30, 0):,.0f} (30d), ${cash.get(60, 0):,.0f} (60d), and ${cash.get(90, 0):,.0f} "
        f"(90d). {base}",
        "",
    ]
    for w in analysis.leakage:
        lines.append(f"- {w.detail} (confidence {w.confidence:.2f}).")
    if analysis.segment_margins:
        worst = min(analysis.segment_margins, key=lambda s: s.margin)
        lines.append("")
        lines.append(
            f"Lowest-margin segment: {worst.segment} at {worst.margin:.1%} "
            f"(${worst.earned_revenue:,.0f} earned)."
        )
    if analysis.leakage:
        top = analysis.leakage[0]
        lines.append(
            f"Recommended action: address {top.name} first (~${top.severity_cents / 100:,.0f} exposure) "
            "via change order / cost review before it compounds."
        )
    return "\n".join(lines)


def _adapt_provider(text: str, provider: str) -> str:
    """Narration-only provider adaptation (ADR 0003 — figures untouched): rename the flagship
    default to the tenant's field-service system and make sure the system of record is named."""
    if provider and provider != "ServiceTitan":
        text = text.replace("ServiceTitan", provider)
        if provider not in text:
            text += f"\n\nField-service system of record: {provider}."
    return text


async def explain(
    analysis: FinancialAnalysis,
    settings: Settings,
    lessons: str = "",
    provider: str = "ServiceTitan",
) -> str:
    # `lessons` = retrieved self-learning memory (past wins/edits). It steers the NARRATION only;
    # the persona below still forbids recomputing any figure, so the numbers stay deterministic.
    # `provider` = the tenant's field-service system display name — wording/metadata only.
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
        + f"\nThe customer's field-service system of record is {provider} — refer"
        " to it by that name."
        + "\nWrite the executive narrative."
    )
    narrative = await narrate(
        agent="financial",
        settings=settings,
        system=[{"type": "text", "text": SYSTEM_PERSONA, "cache_control": {"type": "ephemeral"}}],
        user_content=user_content,
        brief=brief,
        template=template,
    )
    return _adapt_provider(narrative, provider)
