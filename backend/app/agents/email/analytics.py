"""Deterministic email-triage engine: classify -> prioritize -> draft -> benchmark workflows.

No LLM, no randomness (ADR 0003). Buckets every unread email (needs_reply / fyi / trash /
workflow_report), scores reply priority (value + age + commercial-tier bonus), builds template reply
drafts from extracted fields (flagging angry/legal-insurance ones for a human), queues trash with a
confidence + category, and grades each automated workflow against fixed benchmarks — proposing a
deterministic rewrite for an underperformer. The reasoning layer narrates (and may polish draft
WORDING); it never decides. Sending replies, deleting emails, and rewriting workflows are WRITES —
they flow through the action gate per the agent's autonomy policy (ADR 0007).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date

from app.agents.email.models import EmailMessage, InboxData, WorkflowStats

# --- priority score: value + age + commercial-tier bonus (hand-computable) -------------------
VALUE_POINTS_PER_USD = 0.01   # $12,400 bid -> 124 pts: dollars dominate, as they should
AGE_WEIGHT = 1.5              # pts per hour waiting
AGE_CAP_HOURS = 72.0          # an old thread stops out-scoring real money after 3 days
COMMERCIAL_BONUS = 40.0
TOP_PRIORITY_LIMIT = 5

# --- reply drafts -----------------------------------------------------------------------------
REPLY_CONFIDENCE = 0.9
REPLY_CONFIDENCE_HUMAN = 0.6  # angry / legal / insurance threads: draft prepared, human must review
HUMAN_REVIEW_TOPICS = {"legal", "insurance"}

# --- workflow benchmarks (industry baselines for contractor outbound sequences) ---------------
BENCHMARK_OPEN_RATE = 0.35
BENCHMARK_REPLY_RATE = 0.12
UNDERPERFORM_FACTOR = 0.75    # below 75% of a benchmark on either metric -> underperforming

# --- classification ----------------------------------------------------------------------------
TRASH_CATEGORIES = ("promo", "spam", "newsletter")
KNOWN_HINTS = {"needs_reply", "fyi", "workflow_report", *TRASH_CATEGORIES}
HINT_CONFIDENCE = 0.95

# keyword -> bucket fallbacks (used only when the source didn't declare a category). Order matters:
# a spammy "invoice wire transfer" must land in spam before the reply keywords can claim it.
_WORKFLOW_KW = ("workflow report", "automation summary", "sequence report")
_SPAM_KW = ("gift card", "wire transfer", "you've been selected", "claim your prize")
_PROMO_KW = ("% off", "flash sale", "free shipping", "limited time", "last chance", "early-bird")
_NEWSLETTER_KW = ("newsletter", "digest", "issue #", "unsubscribe")
_REPLY_KW = ("?", "bid", "quote", "estimate", "reschedule", "invoice", "claim #", "complaint", "renewal")

_SPAM_CONFIDENCE = 0.90
_PROMO_CONFIDENCE = 0.88
_NEWSLETTER_CONFIDENCE = 0.86
_WORKFLOW_KW_CONFIDENCE = 0.85
_REPLY_KW_CONFIDENCE = 0.80
_FYI_FALLBACK_CONFIDENCE = 0.60


# --------------------------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class PriorityEmail:
    email_id: str
    from_name: str
    subject: str
    reason: str
    value_cents: int | None
    age_hours: float
    priority_score: float


@dataclass(frozen=True)
class ReplyDraft:
    email_id: str
    from_name: str
    from_address: str
    subject: str
    draft_subject: str
    draft_body: str
    confidence: float
    requires_human: bool
    priority_score: float


@dataclass(frozen=True)
class TrashItem:
    email_id: str
    from_name: str
    subject: str
    category: str  # promo | spam | newsletter
    age_days: int
    confidence: float


@dataclass(frozen=True)
class WorkflowRewrite:
    subject: str
    preview: str
    rationale: str


@dataclass(frozen=True)
class WorkflowHealth:
    workflow_id: str
    name: str
    emails_sent: int
    open_rate: float
    reply_rate: float
    booked_jobs: int
    benchmark_open_rate: float
    benchmark_reply_rate: float
    status: str  # healthy | underperforming
    proposed_rewrite: WorkflowRewrite | None


@dataclass(frozen=True)
class InboxTotals:
    unread_total: int
    needs_reply: int
    fyi: int
    trash_candidates: int
    workflow_reports: int


@dataclass(frozen=True)
class EmailAnalysis:
    as_of: date
    totals: InboxTotals
    top_priorities: list[PriorityEmail]
    reply_drafts: list[ReplyDraft]
    trash_queue: list[TrashItem]
    workflows: list[WorkflowHealth]
    inputs_hash: str


# --------------------------------------------------------------------------------------------
# Pure primitives
# --------------------------------------------------------------------------------------------
def classify(email: EmailMessage) -> tuple[str, str | None, float]:
    """-> (bucket, trash_category | None, confidence). Hint wins; keywords are the fallback."""
    hint = (email.category_hint or "").lower()
    if hint in KNOWN_HINTS:
        if hint in TRASH_CATEGORIES:
            return "trash", hint, HINT_CONFIDENCE
        return hint, None, HINT_CONFIDENCE

    text = f"{email.subject} {email.body_excerpt}".lower()
    if any(k in text for k in _WORKFLOW_KW):
        return "workflow_report", None, _WORKFLOW_KW_CONFIDENCE
    if any(k in text for k in _SPAM_KW):
        return "trash", "spam", _SPAM_CONFIDENCE
    if any(k in text for k in _PROMO_KW):
        return "trash", "promo", _PROMO_CONFIDENCE
    if any(k in text for k in _NEWSLETTER_KW):
        return "trash", "newsletter", _NEWSLETTER_CONFIDENCE
    if any(k in text for k in _REPLY_KW):
        return "needs_reply", None, _REPLY_KW_CONFIDENCE
    return "fyi", None, _FYI_FALLBACK_CONFIDENCE


def priority_score(email: EmailMessage) -> float:
    value_usd = (email.value_cents or 0) / 100
    points = value_usd * VALUE_POINTS_PER_USD
    points += min(email.age_hours, AGE_CAP_HOURS) * AGE_WEIGHT
    if (email.customer_tier or "").lower() == "commercial":
        points += COMMERCIAL_BONUS
    return round(points, 2)


def requires_human(email: EmailMessage) -> bool:
    if (email.sentiment or "").lower() == "angry":
        return True
    return (email.topic or "").lower() in HUMAN_REVIEW_TOPICS


def workflow_status(open_rate: float, reply_rate: float) -> str:
    if open_rate < BENCHMARK_OPEN_RATE * UNDERPERFORM_FACTOR:
        return "underperforming"
    if reply_rate < BENCHMARK_REPLY_RATE * UNDERPERFORM_FACTOR:
        return "underperforming"
    return "healthy"


def _first_name(email: EmailMessage) -> str:
    name = (email.customer_name or email.from_name or "there").strip()
    return name.split()[0] if name else "there"


def _amount(email: EmailMessage) -> str:
    return f"${(email.value_cents or 0) / 100:,.0f}"


def _priority_reason(email: EmailMessage) -> str:
    parts: list[str] = []
    if email.value_cents:
        what = (email.intent or "opportunity").replace("_", " ")
        parts.append(f"{_amount(email)} {what}")
    elif email.intent:
        parts.append(email.intent.replace("_", " "))
    if (email.customer_tier or "").lower() == "commercial":
        parts.append("commercial account")
    parts.append(f"waiting {email.age_hours:.0f}h")
    return "; ".join(parts)


def draft_reply(email: EmailMessage) -> tuple[str, str]:
    """Deterministic template (subject, body) from extracted fields. The LLM may polish WORDING when
    enabled; these templates are what ships in fixture/DISABLE_LLM mode."""
    first = _first_name(email)
    job = email.job_type or "your project"
    when = email.requested_date or "this week"
    intent = (email.intent or "").lower()
    subject = f"Re: {email.subject}"

    if intent == "bid_request":
        body = (
            f"Hi {first},\n\nThank you for the invitation to bid on {job}. We can have a detailed "
            f"proposal for the {_amount(email)} scope to you by {when}, including itemized labor, "
            f"equipment, and a project schedule.\n\nIf helpful, we can walk the site first — just "
            f"reply with two times that work.\n\nThank you,\nThe office"
        )
    elif intent in ("estimate_question", "quote_request"):
        body = (
            f"Hi {first},\n\nHappy to put together a quote for {job}. Based on what you described, "
            f"comparable installs run around {_amount(email)}; we'd confirm with a quick on-site "
            f"visit.\n\nDoes {when} work for a 30-minute walkthrough?\n\nThank you,\nThe office"
        )
    elif intent in ("schedule_request", "reschedule_request"):
        body = (
            f"Hi {first},\n\nNo problem at all — we can move {job} to {when}. I have you penciled "
            f"in; reply to confirm and we'll lock it with the technician.\n\nThank you,\nThe office"
        )
    elif intent == "invoice_question":
        body = (
            f"Hi {first},\n\nGood question — let me clarify the charge on that invoice. The line "
            f"item covers {job}, billed at {_amount(email)}. I've attached the itemized breakdown; "
            f"if anything still looks off, reply here and we'll make it right.\n\nThank you,\nThe office"
        )
    elif intent == "contract_renewal":
        body = (
            f"Hi {first},\n\nThank you for renewing with us. I've prepared the renewal at "
            f"{_amount(email)} per year covering {job}, same response times as last term. I'll send "
            f"the agreement for signature — reply with any changes first.\n\nThank you,\nThe office"
        )
    elif intent == "complaint":
        body = (
            f"Hi {first},\n\nI'm sorry — that is not the standard we hold our crews to. I've "
            f"escalated this to our operations manager and we will make it right at no cost to you. "
            f"Expect a call today to schedule the fix.\n\nThank you for telling us,\nThe office"
        )
    elif intent == "insurance_claim":
        body = (
            f"Hi {first},\n\nConfirming receipt regarding the claim. We are assembling the requested "
            f"documentation ({job}) and will send it for review by {when}. Please treat this as an "
            f"acknowledgment only, not an admission or commitment.\n\nThank you,\nThe office"
        )
    else:
        body = (
            f"Hi {first},\n\nThanks for reaching out about {job}. We'll get you a complete answer "
            f"by {when} — reply here if anything is urgent in the meantime.\n\nThank you,\nThe office"
        )
    return subject, body


def propose_workflow_rewrite(w: WorkflowStats, open_rate: float, reply_rate: float) -> WorkflowRewrite:
    """Deterministic rewrite proposal for an underperforming sequence."""
    noun = w.name.lower().replace(" follow-up", "").replace(" request", "").strip() or "project"
    return WorkflowRewrite(
        subject=f"Quick question about your {noun}",
        preview="Reply yes or no and we'll take it from there — 30 seconds, no pressure.",
        rationale=(
            f"Open rate {open_rate:.0%} vs {BENCHMARK_OPEN_RATE:.0%} benchmark and reply rate "
            f"{reply_rate:.0%} vs {BENCHMARK_REPLY_RATE:.0%} benchmark: the current subject reads "
            f"like a mass blast. A short, personal, question-led subject plus a one-line ask "
            f"typically restores opens and invites replies."
        ),
    )


# --------------------------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------------------------
def analyze(data: InboxData) -> EmailAnalysis:
    needs_reply: list[EmailMessage] = []
    fyi_count = 0
    workflow_report_count = 0
    trash: list[TrashItem] = []

    for email in data.emails:
        bucket, trash_category, confidence = classify(email)
        if bucket == "needs_reply":
            needs_reply.append(email)
        elif bucket == "fyi":
            fyi_count += 1
        elif bucket == "workflow_report":
            workflow_report_count += 1
        else:  # trash
            trash.append(
                TrashItem(
                    email_id=email.id,
                    from_name=email.from_name,
                    subject=email.subject,
                    category=trash_category or "promo",
                    age_days=int(email.age_hours // 24),
                    confidence=confidence,
                )
            )

    # --- priorities + drafts (needs_reply only) ---
    scored = sorted(needs_reply, key=lambda e: (-priority_score(e), e.id))
    top_priorities = [
        PriorityEmail(
            email_id=e.id,
            from_name=e.from_name,
            subject=e.subject,
            reason=_priority_reason(e),
            value_cents=e.value_cents,
            age_hours=e.age_hours,
            priority_score=priority_score(e),
        )
        for e in scored[:TOP_PRIORITY_LIMIT]
    ]
    drafts: list[ReplyDraft] = []
    for e in scored:
        human = requires_human(e)
        draft_subject, draft_body = draft_reply(e)
        drafts.append(
            ReplyDraft(
                email_id=e.id,
                from_name=e.from_name,
                from_address=e.from_address,
                subject=e.subject,
                draft_subject=draft_subject,
                draft_body=draft_body,
                confidence=REPLY_CONFIDENCE_HUMAN if human else REPLY_CONFIDENCE,
                requires_human=human,
                priority_score=priority_score(e),
            )
        )

    trash.sort(key=lambda t: (-t.age_days, t.email_id))

    # --- workflow health ---
    workflows: list[WorkflowHealth] = []
    for w in data.workflows:
        open_rate = round(w.opens / w.emails_sent, 4) if w.emails_sent else 0.0
        reply_rate = round(w.replies / w.emails_sent, 4) if w.emails_sent else 0.0
        status = workflow_status(open_rate, reply_rate)
        workflows.append(
            WorkflowHealth(
                workflow_id=w.id,
                name=w.name,
                emails_sent=w.emails_sent,
                open_rate=open_rate,
                reply_rate=reply_rate,
                booked_jobs=w.booked_jobs,
                benchmark_open_rate=BENCHMARK_OPEN_RATE,
                benchmark_reply_rate=BENCHMARK_REPLY_RATE,
                status=status,
                proposed_rewrite=(
                    propose_workflow_rewrite(w, open_rate, reply_rate)
                    if status == "underperforming"
                    else None
                ),
            )
        )

    totals = InboxTotals(
        unread_total=len(data.emails),
        needs_reply=len(needs_reply),
        fyi=fyi_count,
        trash_candidates=len(trash),
        workflow_reports=workflow_report_count,
    )
    return EmailAnalysis(
        as_of=data.as_of,
        totals=totals,
        top_priorities=top_priorities,
        reply_drafts=drafts,
        trash_queue=trash,
        workflows=workflows,
        inputs_hash=_hash_inputs(data),
    )


def _hash_inputs(data: InboxData) -> str:
    payload = {
        "as_of": data.as_of.isoformat(),
        "emails": sorted((asdict(e) for e in data.emails), key=lambda r: r["id"]),
        "workflows": sorted((asdict(w) for w in data.workflows), key=lambda r: r["id"]),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
