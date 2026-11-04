"""Narration (reasoning) layer for the rolling-capacity advisory run.

Mirrors ``payroll_reasoning.py`` and obeys the same ADR-0003 boundary: it NEVER computes a number — it
quotes the deterministic engine's estimates and projections. With ``DISABLE_LLM=1`` or no API key a
deterministic template renders the narrative so the pipeline runs and is testable offline. Learned
``lessons`` and the tenant ``provider`` steer wording only.
"""
from __future__ import annotations

import json

from app.agents._narrate import narrate
from app.agents.workforce.capacity import TechJobTypeDuration, TechWeekProjection
from app.agents.workforce.capacity_schemas import pace_read as _pace
from app.agents.workforce.prompts import SYSTEM_PERSONA
from app.config import Settings

# The faster/slower/on-baseline read is owned by capacity_schemas.pace_read (single source of truth for
# the tolerance) so the narrative can never disagree with the API's ``pace`` field if the threshold is
# tuned. Re-exported here as ``_pace`` to keep the call-sites below unchanged.


def _brief(
    durations: list[TechJobTypeDuration], projections: list[TechWeekProjection]
) -> dict:
    """Compact, authoritative figures handed to the model to narrate (not recompute)."""
    return {
        "durations": [
            {
                "technician_id": d.technician_id,
                "job_type": d.job_type,
                "estimate_hours": d.estimate_hours,
                "baseline_hours": d.baseline_hours,
                "efficiency_delta_hours": d.efficiency_delta_hours,
                "pace": _pace(d.efficiency_delta_hours),
                "sample_size": d.sample_size,
            }
            for d in durations
        ],
        "projections": [
            {
                "technician_id": p.technician_id,
                "job_count": p.job_count,
                "projected_hours": p.projected_hours,
                "contracted_hours": p.contracted_hours,
                "overtime_hours": p.overtime_hours,
                "redistribute_to": list(p.redistribute_to),
            }
            for p in projections
        ],
    }


def _template_narrative(
    durations: list[TechJobTypeDuration], projections: list[TechWeekProjection]
) -> str:
    over = [p for p in projections if p.overtime_hours > 0]
    total_ot = round(sum(p.overtime_hours for p in over), 1)
    lines = [
        f"Rolling capacity: {len(durations)} learned (technician, job-type) duration estimate(s) "
        f"across {len(projections)} technician(s). "
        + (
            f"{len(over)} technician(s) project into overtime next week (+{total_ot}h total) on their "
            "own learned per-job durations."
            if over
            else "No technician projects into overtime next week on their learned per-job durations."
        )
    ]

    faster = [d for d in durations if _pace(d.efficiency_delta_hours) == "faster"]
    slower = [d for d in durations if _pace(d.efficiency_delta_hours) == "slower"]
    if faster or slower:
        lines.append("")
        lines.append("Efficiency vs. job-type baseline (the moving target re-adjusts each completed job):")
        for d in sorted(faster, key=lambda d: d.efficiency_delta_hours):
            lines.append(
                f"- {d.technician_id} is faster than baseline on {d.job_type}: "
                f"{d.estimate_hours:.1f}h vs {d.baseline_hours:.1f}h "
                f"({d.efficiency_delta_hours:+.1f}h, n={d.sample_size})."
            )
        for d in sorted(slower, key=lambda d: d.efficiency_delta_hours, reverse=True):
            lines.append(
                f"- {d.technician_id} is slower than baseline on {d.job_type}: "
                f"{d.estimate_hours:.1f}h vs {d.baseline_hours:.1f}h "
                f"({d.efficiency_delta_hours:+.1f}h, n={d.sample_size})."
            )

    if over:
        lines.append("")
        lines.append("Proactive overtime - flag BEFORE the hours are worked:")
        for p in over:
            tail = (
                f" Same-trade slack to absorb it: {', '.join(p.redistribute_to)}."
                if p.redistribute_to
                else " No same-trade slack; defer lower-priority work or add capacity."
            )
            lines.append(
                f"- {p.technician_id} ({p.trade}): {p.job_count} job(s) -> {p.projected_hours:.1f}h vs "
                f"{p.contracted_hours:.0f}h contracted -> {p.overtime_hours:.1f}h overtime.{tail}"
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
    durations: list[TechJobTypeDuration],
    projections: list[TechWeekProjection],
    settings: Settings,
    lessons: str = "",
    provider: str = "ServiceTitan",
) -> str:
    brief = _brief(durations, projections)
    template = _adapt_provider(_template_narrative(durations, projections), provider)
    user_content = (
        "Here is the authoritative rolling-capacity result (figures are final — quote, "
        "do not recompute):\n```json\n"
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
        + "\nWrite a concise capacity narrative for a dispatch manager: who is getting "
        "faster/slower than baseline, and which technicians project into overtime next "
        "week with which same-trade techs could absorb the overflow."
    )
    narrative = await narrate(
        agent="workforce_capacity",
        settings=settings,
        system=[{"type": "text", "text": SYSTEM_PERSONA, "cache_control": {"type": "ephemeral"}}],
        user_content=user_content,
        brief=brief,
        template=template,
    )
    return _adapt_provider(narrative, provider)
