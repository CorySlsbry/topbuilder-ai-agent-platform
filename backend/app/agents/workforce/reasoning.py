"""The reasoning (narration) layer: turns deterministic results into an executive narrative.

It NEVER computes numbers. With `DISABLE_LLM=1` or no API key, a deterministic template renders the
narrative so the whole pipeline runs and is testable offline (ADR 0003).
"""
from __future__ import annotations

import json

from app.agents._narrate import narrate
from app.agents.workforce.analytics import WorkforceAnalysis
from app.agents.workforce.prompts import SYSTEM_PERSONA
from app.config import Settings


def _analysis_brief(analysis: WorkforceAnalysis) -> dict:
    """Compact, authoritative figures handed to the model to narrate (not recompute)."""
    return {
        "as_of": analysis.as_of.isoformat(),
        "horizon_days": analysis.horizon_days,
        "understaffing_risks": [
            {
                "trade": r.trade,
                "week_start": r.week_start.isoformat(),
                "gap_hours": r.gap_hours,
                "gap_count": r.gap_count,
                "economic_impact_usd": round(r.economic_impact_cents / 100, 2),
                "confidence": r.confidence,
            }
            for r in analysis.understaffing_risks
        ],
        "overtime_risks": [
            {
                "technician": r.technician_name,
                "trade": r.trade,
                "overtime_hours": r.projected_overtime_hours,
                "premium_usd": round(r.economic_impact_cents / 100, 2),
                "mitigation_candidates": r.mitigation_candidates,
                "confidence": r.confidence,
            }
            for r in analysis.overtime_risks
        ],
    }


def _template_narrative(analysis: WorkforceAnalysis) -> str:
    if not analysis.understaffing_risks and not analysis.overtime_risks:
        return (
            "No material staffing gaps or avoidable overtime were detected across the forecast "
            "horizon. Utilization is within target on every trade."
        )

    us_impact = sum(r.economic_impact_cents for r in analysis.understaffing_risks) / 100
    ot_impact = sum(r.economic_impact_cents for r in analysis.overtime_risks) / 100
    lines = [
        f"Across the next {analysis.horizon_days} days, the model flags "
        f"{len(analysis.understaffing_risks)} trade-week(s) at risk of understaffing "
        f"(~${us_impact:,.0f} in at-risk contribution margin) and "
        f"{len(analysis.overtime_risks)} technician(s) trending into avoidable overtime "
        f"(~${ot_impact:,.0f} in premium cost).",
        "",
    ]
    for r in analysis.understaffing_risks:
        lines.append(f"- Understaffing: {r.reasoning} Economic impact ~${r.economic_impact_cents / 100:,.0f} "
                     f"(confidence {r.confidence:.2f}).")
    for r in analysis.overtime_risks:
        lines.append(f"- Overtime: {r.reasoning} (confidence {r.confidence:.2f}).")

    lines.append("")
    actions: list[str] = []
    if analysis.understaffing_risks:
        top = analysis.understaffing_risks[0]
        actions.append(
            f"prioritize covering the {top.trade.upper()} shortfall for the week of "
            f"{top.week_start.isoformat()} ({top.gap_count} technician-week(s))"
        )
    for r in analysis.overtime_risks:
        if r.mitigation_candidates:
            actions.append(
                f"shift load from {r.technician_name} to {', '.join(r.mitigation_candidates)} "
                "before approving overtime"
            )
            break
    if actions:
        lines.append("Recommended actions (highest impact first): " + "; ".join(actions) + ".")
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
    analysis: WorkforceAnalysis,
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
        "Here is the authoritative analysis (figures are final — quote, do not "
        "recompute):\n```json\n"
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
        agent="workforce",
        settings=settings,
        system=[{"type": "text", "text": SYSTEM_PERSONA, "cache_control": {"type": "ephemeral"}}],
        user_content=user_content,
        brief=brief,
        template=template,
    )
    return _adapt_provider(narrative, provider)
