"""Unit + property tests for the deterministic PO/AP-from-email engine.

Hand-computed oracle (5 bills, 3 open jobs):
  - BILL1: printed job# JOB-9001 -> matches -> AUTO_PROPOSE ($480.00 / 48,000¢)
  - BILL2: printed job# JOB-9002 -> matches -> AUTO_PROPOSE ($1,200.00 / 120,000¢)
  - BILL3: handwritten job# JOB-9003 (matches) -> NEEDS_HUMAN (low confidence)
  - BILL4: missing job# -> NEEDS_HUMAN (no number)
  - BILL5: printed job# JOB-9999 (no open job) -> NEEDS_HUMAN (no match)
=> auto_proposed 2 / needs_human 3; auto_value 168,000¢; needs_human_value 95,000¢.
"""
from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.agents.documents import ap
from app.agents.documents.ap_models import OpenJob, VendorBill, VendorBillsData

AS_OF = date(2026, 6, 16)
JOBS = [
    OpenJob("JOB-9001", "Peter Powell — HVAC Install", "Peter Powell"),
    OpenJob("JOB-9002", "Mercer Building — Repipe", "Mercer Building"),
    OpenJob("JOB-9003", "Santos Home — Heat Pump", "Santos Home"),
]


def _bill(bid: str, **kw) -> VendorBill:
    base = {"vendor": "Acme Supply", "amount_cents": 10_000, "doc_number": f"INV-{bid}",
            "bill_date": AS_OF}
    base.update(kw)
    return VendorBill(id=bid, **base)


def _scenario() -> VendorBillsData:
    bills = [
        _bill("BILL1", amount_cents=48_000, extracted_job_ref="JOB-9001", job_ref_source="printed"),
        _bill("BILL2", amount_cents=120_000, extracted_job_ref="JOB-9002", job_ref_source="printed"),
        _bill("BILL3", amount_cents=22_000, extracted_job_ref="JOB-9003", job_ref_source="handwritten"),
        _bill("BILL4", amount_cents=15_000, extracted_job_ref=None, job_ref_source="missing"),
        _bill("BILL5", amount_cents=58_000, extracted_job_ref="JOB-9999", job_ref_source="printed"),
    ]
    return VendorBillsData(as_of=AS_OF, bills=bills, open_jobs=JOBS)


class TestMatchJob:
    def test_exact_match(self) -> None:
        assert ap.match_job(_bill("X", extracted_job_ref="JOB-9001"), JOBS) is JOBS[0]

    def test_normalized_match_ignores_case_and_space(self) -> None:
        assert ap.match_job(_bill("X", extracted_job_ref=" job-9002 "), JOBS) is JOBS[1]

    def test_no_number_no_match(self) -> None:
        assert ap.match_job(_bill("X", extracted_job_ref=None), JOBS) is None

    def test_unknown_number_no_match(self) -> None:
        assert ap.match_job(_bill("X", extracted_job_ref="JOB-0000"), JOBS) is None


class TestScore:
    def test_printed_match_clears_auto_threshold(self) -> None:
        b = _bill("X", extracted_job_ref="JOB-9001", job_ref_source="printed")
        assert ap.score(b, JOBS[0]) >= ap.AUTO_THRESHOLD

    def test_handwritten_below_threshold(self) -> None:
        b = _bill("X", extracted_job_ref="JOB-9003", job_ref_source="handwritten")
        assert ap.score(b, JOBS[2]) < ap.AUTO_THRESHOLD

    def test_no_match_scores_zero(self) -> None:
        assert ap.score(_bill("X", job_ref_source="printed"), None) == 0.0


class TestAnalyzeTotals:
    def test_totals(self) -> None:
        t = ap.analyze(_scenario()).totals
        assert (t.bills_processed, t.auto_proposed, t.needs_human) == (5, 2, 3)
        assert t.auto_value_cents == 168_000          # 48,000 + 120,000
        assert t.needs_human_value_cents == 95_000     # 22,000 + 15,000 + 58,000

    def test_auto_drafts_are_the_clean_printed_matches(self) -> None:
        drafts = {d.bill_id: d for d in ap.analyze(_scenario()).drafts}
        assert set(drafts) == {"BILL1", "BILL2"}
        assert drafts["BILL1"].job_ref == "JOB-9001"
        assert drafts["BILL1"].customer_name == "Peter Powell"
        assert drafts["BILL1"].action == "auto_propose"

    def test_needs_human_reasons(self) -> None:
        nh = {u.bill_id: u.reason.lower() for u in ap.analyze(_scenario()).needs_human}
        assert "handwritten" in nh["BILL3"]            # low-confidence number
        assert "no job number" in nh["BILL4"]          # missing
        assert "did not match" in nh["BILL5"]          # unknown number


class TestInputsHash:
    def test_stable_and_hex(self) -> None:
        h1, h2 = ap.analyze(_scenario()).inputs_hash, ap.analyze(_scenario()).inputs_hash
        assert h1 == h2
        assert len(h1) == 64 and all(c in "0123456789abcdef" for c in h1)

    @given(st.integers(min_value=1, max_value=5_000_000))
    def test_hash_changes_when_amount_changes(self, amount: int) -> None:
        base = _scenario()
        bumped = VendorBillsData(
            as_of=base.as_of,
            bills=[VendorBill(**{**b.__dict__, "amount_cents": b.amount_cents + amount}) for b in base.bills],
            open_jobs=base.open_jobs,
        )
        assert ap.analyze(base).inputs_hash != ap.analyze(bumped).inputs_hash


class TestAnalyzeProperties:
    @given(st.lists(st.sampled_from(["printed", "handwritten", "missing"]), min_size=0, max_size=8))
    def test_every_bill_lands_in_exactly_one_bucket(self, sources: list[str]) -> None:
        bills = [
            _bill(f"B{i}", extracted_job_ref=("JOB-9001" if s != "missing" else None), job_ref_source=s)
            for i, s in enumerate(sources)
        ]
        res = ap.analyze(VendorBillsData(as_of=AS_OF, bills=bills, open_jobs=JOBS))
        assert res.totals.auto_proposed + res.totals.needs_human == len(bills)
        assert res.totals.bills_processed == len(bills)

    def test_only_printed_matched_bills_auto_propose(self) -> None:
        res = ap.analyze(_scenario())
        for d in res.drafts:
            assert d.confidence >= ap.AUTO_THRESHOLD
