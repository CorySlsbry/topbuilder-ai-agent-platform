"""Reasoning (narration) layer for the Pricebook agent. Numbers in, prose out — never computes."""
from __future__ import annotations

import json

from app.agents._narrate import narrate
from app.agents.pricebook.analytics import PricebookAnalysis
from app.agents.pricebook.prompts import SYSTEM_PERSONA
from app.config import Settings


def _usd(cents: int) -> float:
    return round(cents / 100, 2)


def _analysis_brief(analysis: PricebookAnalysis) -> dict:
    t = analysis.totals
    return {
        "as_of": analysis.as_of.isoformat(),
        "tolerance_pct": analysis.tolerance_pct,
        "totals": {
            "items": t.items,
            "items_affected": t.items_affected,
            "items_flagged": t.items_flagged,
            "total_price_delta_usd": _usd(t.total_price_delta_cents),
            "distinct_skus": t.distinct_skus,
            "skus_updated": t.skus_updated,
            "vendor_coverage_pct": t.vendor_coverage_pct,
            "avg_markup_pct": t.avg_markup_pct,
        },
        "changes": [
            {
                "item": c.name,
                "code": c.code,
                "category": c.category,
                "old_price_usd": _usd(c.old_price_cents),
                "new_price_usd": _usd(c.new_price_cents),
                "price_delta_usd": _usd(c.price_delta_cents),
                "price_delta_pct": c.price_delta_pct,
                "old_materials_usd": _usd(c.old_materials_cost_cents),
                "new_materials_usd": _usd(c.new_materials_cost_cents),
                "margin_delta_usd": _usd(c.margin_delta_cents),
                "changed_skus": c.changed_skus,
                "beyond_tolerance": c.beyond_tolerance,
            }
            # Only the items that actually moved are worth narrating.
            for c in analysis.changes
            if c.price_delta_cents != 0
        ],
    }


def _template_narrative(analysis: PricebookAnalysis) -> str:
    t = analysis.totals
    if t.items == 0:
        return "No pricebook items in this batch. Nothing to re-price."

    if t.items_affected == 0:
        return (
            f"Re-priced {t.items} pricebook item(s) against the vendor update — no prices moved. "
            f"The update covered {t.skus_updated} of {t.distinct_skus} SKUs "
            f"({t.vendor_coverage_pct:.0f}% of the catalog), none on items currently priced."
        )

    net = _usd(t.total_price_delta_cents)
    direction = "up" if t.total_price_delta_cents > 0 else "down"
    lines = [
        f"The vendor update moved {t.items_affected} of {t.items} pricebook item(s); net repricing "
        f"impact ${net:,.2f} ({direction}). It covered {t.skus_updated} of {t.distinct_skus} SKUs "
        f"({t.vendor_coverage_pct:.0f}% of the catalog). {t.items_flagged} item(s) moved beyond the "
        f"{analysis.tolerance_pct:.0f}% tolerance and need a human check.",
        "",
    ]

    moved = [c for c in analysis.changes if c.price_delta_cents != 0]
    for c in moved[:4]:
        flag = "  ⚠ beyond tolerance" if c.beyond_tolerance else ""
        skus = ", ".join(c.changed_skus) if c.changed_skus else "—"
        lines.append(
            f"- {c.name} ({c.code}): ${_usd(c.old_price_cents):,.2f} -> ${_usd(c.new_price_cents):,.2f} "
            f"({c.price_delta_pct:+.1f}%), driven by {skus}; margin {c.margin_delta_cents/100:+,.2f}.{flag}"
        )

    flagged = [c for c in moved if c.beyond_tolerance]
    if flagged:
        names = ", ".join(c.code for c in flagged)
        lines.append("")
        lines.append(f"Review before quoting: {names} — confirm the vendor cost, then approve the new price.")
    elif moved:
        top = moved[0]
        lines.append("")
        lines.append(
            f"Recommended: review {top.name} first (largest move, "
            f"${_usd(top.price_delta_cents):+,.2f}), then down the list."
        )
    return "\n".join(lines)


async def explain(
    analysis: PricebookAnalysis,
    settings: Settings,
    lessons: str = "",
) -> str:
    # `lessons` = retrieved self-learning memory (past wins/edits). It steers the NARRATION only;
    # the persona forbids recomputing any figure, so the numbers stay deterministic.
    brief = _analysis_brief(analysis)
    template = _template_narrative(analysis)
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
    return await narrate(
        agent="pricebook",
        settings=settings,
        system=[{"type": "text", "text": SYSTEM_PERSONA, "cache_control": {"type": "ephemeral"}}],
        user_content=user_content,
        brief=brief,
        template=template,
    )
