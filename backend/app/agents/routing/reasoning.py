"""Reasoning (narration) layer for the Routing agent. Numbers in, prose out — never computes."""
from __future__ import annotations

import json

from app.agents._narrate import narrate
from app.agents.routing.analytics import RoutingAnalysis
from app.agents.routing.prompts import SYSTEM_PERSONA, TRIAGE_SYSTEM_PERSONA
from app.agents.routing.triage import TriageAnalysis
from app.config import Settings


def _analysis_brief(analysis: RoutingAnalysis) -> dict:
    t = analysis.totals
    return {
        "as_of": analysis.as_of.isoformat(),
        "totals": {
            "jobs": t.jobs, "assigned": t.assigned, "unassigned": t.unassigned,
            "techs_used": t.techs_used, "drive_minutes_saved": t.drive_minutes_saved,
        },
        "assignments": [
            {"job": s.customer_name, "trade": s.trade, "tech": s.tech_name,
             "arrival_min": s.arrival_min, "drive_minutes": s.drive_minutes}
            for s in analysis.suggestions
        ],
        "unassigned": [{"trade": u.trade, "reason": u.reason} for u in analysis.unassigned],
    }


def _template_narrative(analysis: RoutingAnalysis) -> str:
    t = analysis.totals
    if t.jobs == 0:
        return "No jobs to dispatch for this day."
    lines = [
        f"Dispatch plan for {t.jobs} job(s): {t.assigned} assigned across {t.techs_used} technician(s), "
        f"saving ~{t.drive_minutes_saved} minutes of drive time "
        f"(~{round(t.drive_minutes_saved / 60, 1)} hours) versus a naive plan.",
        "",
    ]
    for s in sorted(analysis.suggestions, key=lambda s: s.arrival_min)[:6]:
        lines.append(
            f"- {s.customer_name} ({s.trade}) -> {s.tech_name}, arrive "
            f"{s.arrival_min // 60:02d}:{s.arrival_min % 60:02d} ({s.drive_minutes}min drive)."
        )
    if analysis.unassigned:
        trades = ", ".join(sorted({u.trade for u in analysis.unassigned}))
        lines.append("")
        lines.append(
            f"Needs a human: {len(analysis.unassigned)} job(s) could not be assigned ({trades}) — "
            "sub out, hire, or reschedule."
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
    analysis: RoutingAnalysis,
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
        "Authoritative dispatch plan (quote, do not recompute):\n```json\n"
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
        + "\nWrite the dispatch brief."
    )
    narrative = await narrate(
        agent="routing",
        settings=settings,
        system=[{"type": "text", "text": SYSTEM_PERSONA, "cache_control": {"type": "ephemeral"}}],
        user_content=user_content,
        brief=brief,
        template=template,
    )
    return _adapt_provider(narrative, provider)


# --------------------------------------------------------------------------------------------
# Triage narration (P1/P2/P3 + revenue-rank + 3-day board)
# --------------------------------------------------------------------------------------------
def _triage_brief(analysis: TriageAnalysis) -> dict:
    t = analysis.totals
    return {
        "as_of": analysis.as_of.isoformat(),
        "totals": {"jobs": t.jobs, "p1": t.p1, "p2": t.p2, "p3": t.p3,
                   "assignable": t.assignable, "needs_human": t.needs_human},
        "triaged": [
            {"job": j.customer_name, "priority": j.priority_label, "trade": j.trade,
             "recommended_tech": j.recommended_tech_name, "assignable": j.assignable}
            for j in analysis.triaged
        ],
        "board": [
            {"day": d.day, "capacity_min": d.capacity_min, "booked_min": d.booked_min,
             "free_min": d.free_min, "over_capacity_min": d.over_capacity_min,
             "utilization_pct": d.utilization_pct, "jobs": d.job_count}
            for d in analysis.board
        ],
        "unassigned_queue": analysis.unassigned_queue,
    }


def _triage_template_narrative(analysis: TriageAnalysis) -> str:
    t = analysis.totals
    if t.jobs == 0:
        return "No unassigned jobs to triage for this dispatch board."
    lines = [
        f"Dispatch triage: {t.jobs} job(s) — {t.p1} P1 (emergency), {t.p2} P2, {t.p3} P3. "
        f"{t.assignable} have a recommended technician; {t.needs_human} need a human.",
        "",
        "Priority order (P1 first; revenue-ranked within priority):",
    ]
    for j in analysis.triaged[:8]:
        tech = j.recommended_tech_name or "NEEDS A HUMAN"
        lines.append(f"- [{j.priority_label}] {j.customer_name} ({j.trade}) -> {tech}")
    lines.append("")
    lines.append("3-day call board:")
    for d in analysis.board:
        flag = f" — OVER by {d.over_capacity_min}min" if d.over_capacity_min else ""
        lines.append(
            f"- {d.day}: {d.job_count} job(s), {d.booked_min}/{d.capacity_min}min booked "
            f"({d.utilization_pct}% util){flag}."
        )
    if analysis.unassigned_queue:
        lines.append("")
        lines.append(
            f"Needs a human ({len(analysis.unassigned_queue)}, P1-first): "
            + ", ".join(analysis.unassigned_queue)
        )
    return "\n".join(lines)


async def explain_triage(
    analysis: TriageAnalysis,
    settings: Settings,
    lessons: str = "",
    provider: str = "ServiceTitan",
) -> str:
    brief = _triage_brief(analysis)
    template = _adapt_provider(_triage_template_narrative(analysis), provider)
    user_content = (
        "Authoritative triage + 3-day board (quote, do not recompute):\n```json\n"
        + json.dumps(brief, indent=2)
        + "\n```"
        + (
            "\n\nLessons from past human feedback on this agent — apply where "
            "relevant, but STILL quote every figure above exactly:\n" + lessons
            if lessons
            else ""
        )
        + f"\nThe customer's field-service system of record is {provider}."
        + "\nWrite the dispatch triage brief."
    )
    narrative = await narrate(
        agent="routing",
        settings=settings,
        system=[{"type": "text", "text": TRIAGE_SYSTEM_PERSONA, "cache_control": {"type": "ephemeral"}}],
        user_content=user_content,
        brief=brief,
        template=template,
    )
    return _adapt_provider(narrative, provider)
