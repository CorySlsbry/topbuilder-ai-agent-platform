"""API schemas (spec-shaped) + mapper for the Email agent.

The response shape is the frontend contract — field names here are load-bearing:
briefing{unread_total,needs_reply,fyi,trash_candidates,workflow_reports,top_priorities[]},
reply_drafts[], trash_queue[], workflows[] (+ proposed_rewrite), narration, reasoning_logs[].
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.agents.email.analytics import EmailAnalysis


def _usd(cents: int | None) -> float | None:
    return None if cents is None else round(cents / 100, 2)


class TopPriorityOut(BaseModel):
    email_id: str
    from_name: str
    subject: str
    reason: str
    value_usd: float | None
    age_hours: float
    priority_score: float


class BriefingOut(BaseModel):
    unread_total: int
    needs_reply: int
    fyi: int
    trash_candidates: int
    workflow_reports: int
    top_priorities: list[TopPriorityOut]


class ReplyDraftOut(BaseModel):
    email_id: str
    from_name: str
    subject: str
    draft_subject: str
    draft_body: str
    confidence: float
    requires_human: bool


class TrashItemOut(BaseModel):
    email_id: str
    from_name: str
    subject: str
    category: str  # promo | spam | newsletter
    age_days: int
    confidence: float


class WorkflowRewriteOut(BaseModel):
    subject: str
    preview: str
    rationale: str


class AppliedRewriteOut(BaseModel):
    """Copy an operator (usually via the in-app assistant) has APPLIED to this sequence —
    distinct from `proposed_rewrite`, which is the engine's deterministic suggestion."""
    subject: str
    preview: str
    applied_by: str
    applied_at: str


class WorkflowOut(BaseModel):
    workflow_id: str
    name: str
    emails_sent: int
    open_rate: float
    reply_rate: float
    booked_jobs: int
    benchmark_open_rate: float
    benchmark_reply_rate: float
    status: str  # healthy | underperforming
    proposed_rewrite: WorkflowRewriteOut | None = None
    applied_rewrite: AppliedRewriteOut | None = None


class EmailRunResult(BaseModel):
    run_id: uuid.UUID | None = None
    agent: str = "email"
    source_system: str = "ServiceTitan"  # the tenant's field-service system of record (fsm_provider)
    analysis_timestamp: datetime
    as_of: date
    briefing: BriefingOut
    reply_drafts: list[ReplyDraftOut]
    trash_queue: list[TrashItemOut]
    workflows: list[WorkflowOut]
    narration: str
    reasoning_logs: list[str]
    inputs_hash: str


def build_result(
    analysis: EmailAnalysis,
    *,
    narrative: str,
    analysis_timestamp: datetime,
    run_id: uuid.UUID | None = None,
    polished: dict[str, dict[str, str]] | None = None,
    source_system: str = "ServiceTitan",
) -> EmailRunResult:
    polished = polished or {}
    t = analysis.totals
    briefing = BriefingOut(
        unread_total=t.unread_total,
        needs_reply=t.needs_reply,
        fyi=t.fyi,
        trash_candidates=t.trash_candidates,
        workflow_reports=t.workflow_reports,
        top_priorities=[
            TopPriorityOut(
                email_id=p.email_id, from_name=p.from_name, subject=p.subject, reason=p.reason,
                value_usd=_usd(p.value_cents), age_hours=p.age_hours, priority_score=p.priority_score,
            )
            for p in analysis.top_priorities
        ],
    )
    reply_drafts = [
        ReplyDraftOut(
            email_id=d.email_id,
            from_name=d.from_name,
            subject=d.subject,
            draft_subject=polished.get(d.email_id, {}).get("draft_subject", d.draft_subject),
            draft_body=polished.get(d.email_id, {}).get("draft_body", d.draft_body),
            confidence=d.confidence,
            requires_human=d.requires_human,
        )
        for d in analysis.reply_drafts
    ]
    trash_queue = [
        TrashItemOut(
            email_id=i.email_id, from_name=i.from_name, subject=i.subject,
            category=i.category, age_days=i.age_days, confidence=i.confidence,
        )
        for i in analysis.trash_queue
    ]
    workflows = [
        WorkflowOut(
            workflow_id=w.workflow_id, name=w.name, emails_sent=w.emails_sent,
            open_rate=w.open_rate, reply_rate=w.reply_rate, booked_jobs=w.booked_jobs,
            benchmark_open_rate=w.benchmark_open_rate, benchmark_reply_rate=w.benchmark_reply_rate,
            status=w.status,
            proposed_rewrite=(
                WorkflowRewriteOut(
                    subject=w.proposed_rewrite.subject,
                    preview=w.proposed_rewrite.preview,
                    rationale=w.proposed_rewrite.rationale,
                )
                if w.proposed_rewrite is not None
                else None
            ),
        )
        for w in analysis.workflows
    ]
    reasoning_logs = [
        f"triage: {t.unread_total} unread -> needs_reply={t.needs_reply} fyi={t.fyi} "
        f"trash={t.trash_candidates} workflow_reports={t.workflow_reports}",
        *(
            f"workflow:{w.workflow_id} {w.name}: open {w.open_rate:.0%}/{w.benchmark_open_rate:.0%} "
            f"reply {w.reply_rate:.0%}/{w.benchmark_reply_rate:.0%} -> {w.status}"
            for w in analysis.workflows
        ),
    ]
    return EmailRunResult(
        run_id=run_id,
        source_system=source_system,
        analysis_timestamp=analysis_timestamp,
        as_of=analysis.as_of,
        briefing=briefing,
        reply_drafts=reply_drafts,
        trash_queue=trash_queue,
        workflows=workflows,
        narration=narrative,
        reasoning_logs=reasoning_logs,
        inputs_hash=analysis.inputs_hash,
    )
