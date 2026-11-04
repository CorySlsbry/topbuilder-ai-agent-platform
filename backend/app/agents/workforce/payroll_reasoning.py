"""Narration (reasoning) layer for the payroll advisory run.

Mirrors ``workforce/reasoning.py`` and obeys the same ADR-0003 boundary: it NEVER computes a number.
With ``DISABLE_LLM=1`` or no API key, a deterministic template renders the narrative so the pipeline
runs and is testable offline. Learned ``lessons`` and the tenant ``provider`` steer wording only.
"""
from __future__ import annotations

import json

from app.agents._narrate import narrate
from app.agents.workforce.payroll import PayrollRun
from app.agents.workforce.prompts import SYSTEM_PERSONA
from app.config import Settings


def _brief(run: PayrollRun) -> dict:
    """Compact, authoritative figures handed to the model to narrate (not recompute)."""
    return {
        "period": [run.period_start.isoformat(), run.period_end.isoformat()],
        "total_gross_usd": round(run.total_gross_cents / 100, 2),
        "flagged_count": run.flagged_count,
        "workers": [
            {
                "name": wp.worker_name,
                "pay_class": wp.pay_class,
                "gross_usd": round(wp.gross_pay_cents / 100, 2),
                "computed_hours": wp.computed_hours,
                "claimed_hours": wp.claimed_hours,
                "hours_discrepancy": wp.hours_discrepancy,
                "needs_review": wp.needs_review,
            }
            for wp in run.worker_pays
        ],
    }


def _template_narrative(run: PayrollRun) -> str:
    gross = run.total_gross_cents / 100
    lines = [
        f"Payroll for {run.period_start.isoformat()} to {run.period_end.isoformat()}: "
        f"{len(run.worker_pays)} worker(s), ${gross:,.2f} gross. "
        + (
            f"{run.flagged_count} worker(s) have a pay-form vs clock discrepancy that needs review "
            "before posting the adjustment."
            if run.flagged_count
            else "No pay-form discrepancies — every worker's claimed hours match the clock."
        ),
    ]
    flagged = [wp for wp in run.worker_pays if wp.needs_review]
    if flagged:
        lines.append("")
        lines.append("Needs review (highest discrepancy first):")
        for wp in flagged:
            lines.append(
                f"- {wp.worker_name} ({wp.pay_class}): claimed {wp.claimed_hours:.1f}h vs clocked "
                f"{wp.computed_hours:.1f}h ({wp.hours_discrepancy:+.1f}h)."
            )
    return "\n".join(lines)


def _adapt_provider(text: str, provider: str) -> str:
    """Narration-only provider adaptation (ADR 0003 — figures untouched)."""
    if provider and provider != "ServiceTitan":
        text = text.replace("ServiceTitan", provider)
        if provider not in text:
            text += f"\n\nField-service system of record: {provider}."
    return text


async def explain(
    run: PayrollRun,
    settings: Settings,
    lessons: str = "",
    provider: str = "ServiceTitan",
) -> str:
    brief = _brief(run)
    template = _adapt_provider(_template_narrative(run), provider)
    user_content = (
        "Here is the authoritative payroll result (figures are final — quote, do not "
        "recompute):\n```json\n"
        + json.dumps(brief, indent=2)
        + "\n```"
        + (
            "\n\nLessons from past human feedback on this agent — apply where "
            "relevant, but STILL quote every figure above exactly:\n" + lessons
            if lessons
            else ""
        )
        + f"\nThe customer's field-service system of record is {provider} — refer to "
        "it by that name."
        + "\nWrite a concise payroll-review narrative for the payroll clerk."
    )
    narrative = await narrate(
        agent="payroll",
        settings=settings,
        system=[{"type": "text", "text": SYSTEM_PERSONA, "cache_control": {"type": "ephemeral"}}],
        user_content=user_content,
        brief=brief,
        template=template,
    )
    return _adapt_provider(narrative, provider)
