"""Reasoning (narration) layer for the Email agent. Numbers in, prose out — never computes.

Two LLM touchpoints, both on the narration side of the ADR-0003 firewall:
  * `explain` — the morning-briefing narrative (template fallback, like every other agent).
  * `polish_drafts` — optional WORDING polish of the deterministic reply-draft templates. It may only
    rephrase `draft_subject`/`draft_body`; ids, confidences, and `requires_human` flags are figures
    and never pass through it. Fixture/DISABLE_LLM mode returns {} so the templates ship verbatim.
"""
from __future__ import annotations

import json

from app.agents import _telemetry
from app.agents._narrate import narrate
from app.agents.email.analytics import EmailAnalysis
from app.agents.email.prompts import SYSTEM_PERSONA
from app.config import Settings


def _analysis_brief(analysis: EmailAnalysis) -> dict:
    t = analysis.totals
    return {
        "as_of": analysis.as_of.isoformat(),
        "totals": {
            "unread_total": t.unread_total, "needs_reply": t.needs_reply, "fyi": t.fyi,
            "trash_candidates": t.trash_candidates, "workflow_reports": t.workflow_reports,
        },
        "top_priorities": [
            {"from": p.from_name, "subject": p.subject, "reason": p.reason,
             "value_usd": None if p.value_cents is None else round(p.value_cents / 100, 2),
             "priority_score": p.priority_score}
            for p in analysis.top_priorities
        ],
        "reply_drafts": [
            {"to": d.from_name, "subject": d.subject, "requires_human": d.requires_human}
            for d in analysis.reply_drafts
        ],
        "trash": [{"from": t_.from_name, "category": t_.category} for t_ in analysis.trash_queue],
        "workflows": [
            {"name": w.name, "status": w.status, "open_rate": w.open_rate, "reply_rate": w.reply_rate,
             "benchmark_open_rate": w.benchmark_open_rate, "benchmark_reply_rate": w.benchmark_reply_rate}
            for w in analysis.workflows
        ],
    }


def _template_narrative(analysis: EmailAnalysis) -> str:
    t = analysis.totals
    if t.unread_total == 0:
        return "Inbox zero — no unread email to triage."
    lines = [
        f"Inbox triaged: {t.unread_total} unread -> {t.needs_reply} need a reply, {t.fyi} FYI, "
        f"{t.trash_candidates} ready to trash, {t.workflow_reports} workflow reports.",
        "",
    ]
    if analysis.top_priorities:
        top = analysis.top_priorities[0]
        value = f" (${(top.value_cents or 0) / 100:,.0f})" if top.value_cents else ""
        lines.append(f"- Top priority: {top.from_name} — \"{top.subject}\"{value}. {top.reason}.")
    held = [d for d in analysis.reply_drafts if d.requires_human]
    if analysis.reply_drafts:
        lines.append(
            f"- {len(analysis.reply_drafts)} reply draft(s) ready for review"
            + (f"; {len(held)} held for a human ({', '.join(d.from_name for d in held)})." if held else ".")
        )
    if analysis.trash_queue:
        lines.append(f"- {len(analysis.trash_queue)} email(s) queued for cleanup — approve to clear.")
    for w in analysis.workflows:
        if w.status == "underperforming":
            lines.append(
                f"- Workflow \"{w.name}\" is underperforming: open {w.open_rate:.0%} vs "
                f"{w.benchmark_open_rate:.0%} benchmark, reply {w.reply_rate:.0%} vs "
                f"{w.benchmark_reply_rate:.0%}. A rewrite is proposed."
            )
    if analysis.reply_drafts or analysis.trash_queue:
        lines.append("")
        lines.append(
            "Recommended action: approve the ready replies, clear the trash queue, then review the "
            "held drafts and the proposed workflow rewrite."
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
    analysis: EmailAnalysis,
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
        "Authoritative inbox analysis (quote, do not recompute):\n```json\n"
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
        + "\nWrite the morning briefing."
    )
    narrative = await narrate(
        agent="email",
        settings=settings,
        system=[{"type": "text", "text": SYSTEM_PERSONA, "cache_control": {"type": "ephemeral"}}],
        user_content=user_content,
        brief=brief,
        template=template,
    )
    return _adapt_provider(narrative, provider)


async def polish_drafts(
    analysis: EmailAnalysis, settings: Settings, provider: str = "ServiceTitan"
) -> dict[str, dict[str, str]]:
    """-> {email_id: {"draft_subject", "draft_body"}} wording overrides, or {} (fixture/DISABLE_LLM/
    any error -> the deterministic templates ship unchanged). Never touches flags or confidences."""
    if settings.disable_llm or not settings.anthropic_api_key or not analysis.reply_drafts:
        return {}
    try:
        from app.assistant.llm_client import build_llm_client

        drafts_in = {
            d.email_id: {"to": d.from_name, "original_subject": d.subject,
                         "draft_subject": d.draft_subject, "draft_body": d.draft_body}
            for d in analysis.reply_drafts
        }
        client = build_llm_client(settings)
        response = await client.messages.create(
            model=settings.workforce_reasoning_model,
            max_tokens=2000,
            system=(
                "You polish the WORDING of reply-draft emails for a contractor's office. Keep every "
                "fact, name, dollar amount, and date exactly as written — you may only improve tone "
                "and flow. The customer's field-service system of record is "
                f"{provider} — refer to it by that name. Return ONLY a JSON object mapping email_id "
                'to {"draft_subject": str, "draft_body": str}. No commentary.'
            ),
            messages=[{"role": "user", "content": json.dumps(drafts_in, indent=2)}],
        )
        _telemetry.record_usage(
            model=settings.workforce_reasoning_model, usage=getattr(response, "usage", None)
        )
        text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("{"):text.rfind("}") + 1]
        parsed = json.loads(text)
        valid_ids = set(drafts_in)
        out: dict[str, dict[str, str]] = {}
        for email_id, fields in parsed.items():
            if email_id not in valid_ids or not isinstance(fields, dict):
                continue
            subject, body = fields.get("draft_subject"), fields.get("draft_body")
            if isinstance(subject, str) and isinstance(body, str) and subject and body:
                out[email_id] = {"draft_subject": subject, "draft_body": body}
        return out
    except Exception:
        return {}
