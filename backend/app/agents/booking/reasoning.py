"""Reasoning (narration) layer for the Booking agent. Numbers in, prose out — never computes."""
from __future__ import annotations

import json

from app.agents._narrate import narrate
from app.agents.booking.analytics import BookingAnalysis
from app.agents.booking.prompts import SYSTEM_PERSONA
from app.config import Settings


def _after_hours_recovered_cents(analysis: BookingAnalysis) -> int:
    return sum(b.estimated_value_cents for b in analysis.proposed_bookings if b.after_hours)


def _analysis_brief(analysis: BookingAnalysis) -> dict:
    return {
        "as_of": analysis.as_of.isoformat(),
        "totals": {
            "intakes_received": analysis.totals.intakes_received,
            "qualified": analysis.totals.qualified,
            "proposed_bookings": analysis.totals.proposed_bookings,
            "after_hours_captured": analysis.totals.after_hours_captured,
            "recovered_revenue_usd": round(analysis.totals.recovered_revenue_cents / 100, 2),
            "after_hours_recovered_usd": round(_after_hours_recovered_cents(analysis) / 100, 2),
        },
        "proposed_bookings": [
            {
                "caller": b.caller_name,
                "trade": b.trade,
                "urgency": b.urgency,
                "after_hours": b.after_hours,
                "proposed_date": b.proposed_date.isoformat(),
                "value_usd": round(b.estimated_value_cents / 100, 2),
                "confidence": b.confidence,
            }
            for b in analysis.proposed_bookings
        ],
        "unbooked": [{"trade": u.trade, "reason": u.reason} for u in analysis.unbooked],
    }


def _template_narrative(analysis: BookingAnalysis) -> str:
    t = analysis.totals
    if t.intakes_received == 0:
        return "No inbound intakes in this batch. Nothing to qualify or book."

    recovered = t.recovered_revenue_cents / 100
    after_hours = _after_hours_recovered_cents(analysis) / 100
    lines = [
        f"Across {t.intakes_received} inbound intake(s), the agent qualified {t.qualified} and "
        f"produced {t.proposed_bookings} proposed booking(s) — recovering ~${recovered:,.0f} in "
        f"revenue, ~${after_hours:,.0f} of it from after-hours calls "
        f"({t.after_hours_captured} booked after hours) that would otherwise have been missed.",
        "",
    ]

    emergencies = [b for b in analysis.proposed_bookings if b.urgency in {"emergency", "same_day"}]
    for b in sorted(emergencies, key=lambda b: -b.estimated_value_cents)[:3]:
        lines.append(
            f"- {b.urgency.replace('_', '-').title()} {b.trade} for "
            f"{b.caller_name or 'caller'}: slot {b.proposed_date.isoformat()}, "
            f"~${b.estimated_value_cents / 100:,.0f} (confidence {b.confidence:.2f})."
        )

    no_slot = [u for u in analysis.unbooked if "availability" in u.reason.lower()]
    if no_slot:
        trades = ", ".join(sorted({u.trade for u in no_slot}))
        lines.append(
            f"- Needs a human: {len(no_slot)} qualified intake(s) had no open slot "
            f"({trades} booked solid) — hand to dispatch before they go elsewhere."
        )

    screened = [u for u in analysis.unbooked if "availability" not in u.reason.lower()]
    if screened:
        lines.append(f"- Screened out {len(screened)} non-job intake(s) (spam / wrong number / out of area).")

    if analysis.proposed_bookings:
        top = max(analysis.proposed_bookings, key=lambda b: b.estimated_value_cents)
        lines.append("")
        lines.append(
            f"Recommended action: confirm {top.caller_name or 'the highest-value booking'} "
            f"({top.trade}, ~${top.estimated_value_cents / 100:,.0f}) first, then work the emergency queue."
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
    analysis: BookingAnalysis,
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
        agent="booking",
        settings=settings,
        system=[{"type": "text", "text": SYSTEM_PERSONA, "cache_control": {"type": "ephemeral"}}],
        user_content=user_content,
        brief=brief,
        template=template,
    )
    return _adapt_provider(narrative, provider)
