"""Reasoning (narration) layer for the Inventory agent. Numbers in, prose out — never computes."""
from __future__ import annotations

import json

from app.agents._narrate import narrate
from app.agents.inventory.analytics import InventoryAnalysis
from app.agents.inventory.proration import ConsumableProrationAnalysis
from app.agents.inventory.prompts import SYSTEM_PERSONA
from app.config import Settings


def _analysis_brief(analysis: InventoryAnalysis) -> dict:
    return {
        "as_of": analysis.as_of.isoformat(),
        "critical_reorders": [
            {"sku": r.sku, "name": r.name, "days_to_stockout": r.days_to_stockout,
             "exposure_usd": round(r.stockout_exposure_cents / 100, 2), "margin_class": r.margin_class}
            for r in analysis.critical_reorders
        ],
        "shrinkage_usd": round(sum(s.shrinkage_value_cents for s in analysis.shrinkage_alerts) / 100, 2),
        "unbilled_usd": round(sum(u.unbilled_value_cents for u in analysis.unbilled_materials) / 100, 2),
        "arbitrage_annual_usd": round(sum(o.annual_savings_cents for o in analysis.arbitrage) / 100, 2),
    }


def _template_narrative(analysis: InventoryAnalysis) -> str:
    shrink = sum(s.shrinkage_value_cents for s in analysis.shrinkage_alerts) / 100
    unbilled = sum(u.unbilled_value_cents for u in analysis.unbilled_materials) / 100
    arb = sum(o.annual_savings_cents for o in analysis.arbitrage) / 100
    lines = [
        f"{len(analysis.critical_reorders)} part(s) need reordering; "
        f"recoverable now: ~${shrink:,.0f} shrinkage + ~${unbilled:,.0f} unbilled materials, plus "
        f"~${arb:,.0f}/yr in vendor-arbitrage savings.",
        "",
    ]
    for r in analysis.critical_reorders[:5]:
        dts = f"{r.days_to_stockout:.1f}d to stockout" if r.days_to_stockout is not None else "no usage"
        lines.append(f"- Reorder {r.name} ({r.sku}): {dts}, order {r.recommended_order_qty}; "
                     f"exposure ~${r.stockout_exposure_cents / 100:,.0f} (confidence {r.confidence:.2f}).")
    for s in analysis.shrinkage_alerts[:3]:
        lines.append(f"- Shrinkage: {s.reasoning}")
    for o in analysis.arbitrage[:2]:
        lines.append(f"- Arbitrage: {o.reasoning}")
    if analysis.critical_reorders:
        top = max(analysis.critical_reorders, key=lambda r: r.stockout_exposure_cents)
        lines.append("")
        lines.append(f"Recommended action: expedite {top.name} first (highest stockout exposure).")
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
    analysis: InventoryAnalysis,
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
        agent="inventory",
        settings=settings,
        system=[{"type": "text", "text": SYSTEM_PERSONA, "cache_control": {"type": "ephemeral"}}],
        user_content=user_content,
        brief=brief,
        template=template,
    )
    return _adapt_provider(narrative, provider)


def _proration_template(analysis: ConsumableProrationAnalysis) -> str:
    """Deterministic narration for the consumable-proration view. Quotes engine figures, never
    recomputes (ADR 0003)."""
    prorated = analysis.total_prorated_cents / 100
    miscost = analysis.total_miscost_corrected_cents / 100
    lines = [
        f"{len(analysis.lots)} consumable lot(s) prorated across the jobs they served — "
        f"${prorated:,.0f} of material cost reallocated off the single replenish job, correcting "
        f"~${miscost:,.0f} of job-costing error vs the current dump-on-one-job approach.",
        "",
    ]
    for lot in analysis.lots[:5]:
        lines.append(
            f"- {lot.name} ({lot.sku}): ${lot.total_cost_cents / 100:,.0f} lot over "
            f"{lot.job_count} jobs by {lot.method}; today dumped on {lot.dump_job_id} "
            f"(corrects ${lot.miscost_corrected_cents / 100:,.0f})."
        )
        for a in lot.allocations:
            lines.append(f"    · {a.job_id}: ${a.allocated_cost_cents / 100:,.2f} ({a.share_pct:g}%)")
    if analysis.lots:
        top = analysis.lots[0]
        lines.append("")
        lines.append(
            f"Recommended action: log per-job draw on {top.name} first (largest miscost correction)."
        )
    return "\n".join(lines)


async def explain_proration(
    analysis: ConsumableProrationAnalysis,
    settings: Settings,
    lessons: str = "",
    provider: str = "ServiceTitan",
) -> str:
    """Narrate the consumable-proration analysis. Deterministic template path is always available;
    the figures come from the pure engine and are never recomputed here."""
    return _adapt_provider(_proration_template(analysis), provider)
