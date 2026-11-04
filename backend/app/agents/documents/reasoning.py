"""Reasoning (narration) layer for the Documents agent. Numbers in, prose out — never computes."""
from __future__ import annotations

import json

from app.agents._narrate import narrate
from app.agents.documents.analytics import DocumentsAnalysis
from app.agents.documents.prompts import SYSTEM_PERSONA
from app.config import Settings


def _analysis_brief(analysis: DocumentsAnalysis) -> dict:
    t = analysis.totals
    return {
        "as_of": analysis.as_of.isoformat(),
        "totals": {
            "documents_processed": t.documents_processed, "auto_filed": t.auto_filed,
            "needs_signature": t.needs_signature, "needs_human": t.needs_human,
            "expiring_soon": t.expiring_soon, "extracted_value_usd": round(t.extracted_value_cents / 100, 2),
        },
        "filings": [
            {"file": f.filename, "type": f.doc_type, "customer": f.customer_name,
             "to": f"{f.department}/{f.st_folder}", "action": f.action}
            for f in analysis.filings
        ],
        "needs_human": [{"file": u.filename, "type": u.doc_type, "reason": u.reason} for u in analysis.needs_human],
    }


def _template_narrative(analysis: DocumentsAnalysis) -> str:
    t = analysis.totals
    if t.documents_processed == 0:
        return "No new documents to process."
    lines = [
        f"Processed {t.documents_processed} document(s): {t.auto_filed} auto-filed to the right "
        f"customer + ServiceTitan folder, with ${round(t.extracted_value_cents / 100):,} in extracted "
        f"invoice/estimate value.",
        "",
    ]
    if t.needs_signature:
        lines.append(f"- {t.needs_signature} contract(s) need an e-signature — route for signing.")
    if t.expiring_soon:
        coi = [f for f in analysis.filings if f.action == "expiring"]
        names = ", ".join(f.customer_name for f in coi)
        lines.append(f"- {t.expiring_soon} insurance COI(s) expiring within 30 days ({names}) — flag compliance.")
    for u in analysis.needs_human:
        lines.append(f"- Needs a human: {u.filename} — {u.reason}.")
    if t.auto_filed:
        lines.append("")
        lines.append("Recommended action: approve the auto-file batch, then clear the signature + compliance flags.")
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
    analysis: DocumentsAnalysis,
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
        "Authoritative document analysis (quote, do not recompute):\n```json\n"
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
        + "\nWrite the operations brief."
    )
    narrative = await narrate(
        agent="documents",
        settings=settings,
        system=[{"type": "text", "text": SYSTEM_PERSONA, "cache_control": {"type": "ephemeral"}}],
        user_content=user_content,
        brief=brief,
        template=template,
    )
    return _adapt_provider(narrative, provider)
