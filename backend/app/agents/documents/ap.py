"""Deterministic PO/AP-from-email engine: parse a bill -> match the job -> propose an A/P entry.

No LLM, no randomness. For each inbound vendor bill the engine resolves the job number (read off the
PO/invoice by the extraction layer), matches it to an open ServiceTitan job, and proposes an A/P entry.
CONFIDENCE comes from HOW cleanly the job number was obtained — a clean printed number that matches an
open job auto-proposes (Alex's ~90%); a missing or handwritten/unmatched number routes to a human
(~10%). Creating the A/P draft is a WRITE — it flows through the action gate (ADR 0007). The reasoning
layer narrates; it never decides (ADR 0003). Money stays integer cents.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date

from app.agents.documents.ap_models import OpenJob, VendorBill, VendorBillsData

# How a job number was read off the bill -> base confidence in the auto-match.
_SOURCE_CONFIDENCE: dict[str, float] = {
    "printed": 0.92,      # clean printed PO/job number — the ~90% auto lane
    "handwritten": 0.45,  # low-confidence OCR of a handwritten number — needs a human
    "missing": 0.0,       # no job number on the bill at all
}
# A bill auto-proposes only at/above this confidence (i.e. a clean printed number that matched a job).
AUTO_THRESHOLD = 0.85


@dataclass(frozen=True)
class ApDraft:
    """A proposed A/P entry for a matched vendor bill (auto-proposed when confidence clears the bar)."""

    bill_id: str
    vendor: str
    doc_number: str
    amount_cents: int
    job_ref: str
    job_name: str
    customer_name: str
    confidence: float
    action: str  # "auto_propose" | "needs_human"
    reasoning: str


@dataclass(frozen=True)
class UnmatchedBill:
    """A bill we cannot confidently cost to a job — routed to a human (missing/handwritten/no match)."""

    bill_id: str
    vendor: str
    doc_number: str
    amount_cents: int
    extracted_job_ref: str | None
    job_ref_source: str
    reason: str


@dataclass(frozen=True)
class ApTotals:
    bills_processed: int
    auto_proposed: int
    needs_human: int
    auto_value_cents: int      # total $ of the auto-proposed drafts
    needs_human_value_cents: int


@dataclass(frozen=True)
class ApAnalysis:
    as_of: date
    drafts: list[ApDraft]
    needs_human: list[UnmatchedBill]
    totals: ApTotals
    inputs_hash: str


def _normalize_ref(s: str) -> str:
    return "".join(s.lower().split())


def match_job(bill: VendorBill, jobs: list[OpenJob]) -> OpenJob | None:
    """Match a bill's extracted job number to an open job (exact, normalized). None if no number/match."""
    if not bill.extracted_job_ref:
        return None
    target = _normalize_ref(bill.extracted_job_ref)
    for job in jobs:
        if _normalize_ref(job.ref) == target:
            return job
    return None


def score(bill: VendorBill, matched: OpenJob | None) -> float:
    """Confidence in auto-posting this bill's A/P entry: 0 unless a clean job# matched an open job."""
    if matched is None:
        return 0.0
    return _SOURCE_CONFIDENCE.get(bill.job_ref_source, 0.0)


def analyze(data: VendorBillsData) -> ApAnalysis:
    drafts: list[ApDraft] = []
    needs_human: list[UnmatchedBill] = []

    for bill in data.bills:
        matched = match_job(bill, data.open_jobs)
        confidence = score(bill, matched)

        if matched is not None and confidence >= AUTO_THRESHOLD:
            drafts.append(
                ApDraft(
                    bill_id=bill.id, vendor=bill.vendor, doc_number=bill.doc_number,
                    amount_cents=bill.amount_cents, job_ref=matched.ref, job_name=matched.name,
                    customer_name=matched.customer_name, confidence=confidence, action="auto_propose",
                    reasoning=(
                        f"{bill.vendor} bill {bill.doc_number} (${bill.amount_cents / 100:,.2f}): "
                        f"printed job# {matched.ref} matched {matched.name} (conf {confidence:.2f}); "
                        f"propose A/P entry + attach to job."
                    ),
                )
            )
            continue

        # Everything else needs a human: no job number, handwritten/low-confidence, or no open-job match.
        if not bill.extracted_job_ref:
            reason = "no job number on the bill — needs a human to identify the job"
        elif matched is None:
            reason = f"job number '{bill.extracted_job_ref}' did not match any open job"
        else:  # matched but the number was handwritten/low-confidence
            reason = (
                f"job number '{bill.extracted_job_ref}' was {bill.job_ref_source} "
                f"(low confidence) — verify before posting A/P"
            )
        needs_human.append(
            UnmatchedBill(
                bill_id=bill.id, vendor=bill.vendor, doc_number=bill.doc_number,
                amount_cents=bill.amount_cents, extracted_job_ref=bill.extracted_job_ref,
                job_ref_source=bill.job_ref_source, reason=reason,
            )
        )

    totals = ApTotals(
        bills_processed=len(data.bills),
        auto_proposed=len(drafts),
        needs_human=len(needs_human),
        auto_value_cents=sum(d.amount_cents for d in drafts),
        needs_human_value_cents=sum(u.amount_cents for u in needs_human),
    )
    return ApAnalysis(data.as_of, drafts, needs_human, totals, _hash_inputs(data))


def _hash_inputs(data: VendorBillsData) -> str:
    payload = {
        "as_of": data.as_of.isoformat(),
        "bills": sorted((asdict(b) for b in data.bills), key=lambda r: r["id"]),
        "open_jobs": sorted((asdict(j) for j in data.open_jobs), key=lambda r: r["ref"]),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
