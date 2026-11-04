"""DB-free integration of the documents agent's two extra lanes (A6 PO/AP, A10 warranty).

Exercises the fixture adapter -> assemble_documents_data -> the AP + warranty engines -> the service's
recommendation/reasoning rows + the schema sections, so the fixtures and wiring are verified without a
Postgres dependency. Oracle is the bundled fixtures (vendor_bills.json / open_jobs.json /
installed_equipment.json).
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

from app.agents.documents import ap as ap_engine
from app.agents.documents import warranty as warranty_engine
from app.agents.documents.analytics import analyze as analyze_docs
from app.agents.documents.ap_models import VendorBillsData
from app.agents.documents.data import assemble_documents_data
from app.agents.documents.schemas import build_result
from app.agents.documents.service import _recommendation_rows, _reasoning_rows
from app.agents.documents.warranty_models import WarrantyData
from app.integrations.documents.fixture_client import FixtureDocumentsClient

AS_OF = date(2026, 6, 16)


def _bundle():
    return asyncio.run(assemble_documents_data(FixtureDocumentsClient(), as_of=AS_OF))


def _analyses():
    data = _bundle()
    docs = analyze_docs(data)
    ap = ap_engine.analyze(VendorBillsData(as_of=data.as_of, bills=data.vendor_bills, open_jobs=data.open_jobs))
    wr = warranty_engine.analyze(WarrantyData(as_of=data.as_of, equipment=data.installed_equipment))
    return docs, ap, wr


class TestFixtureAssembly:
    def test_bundle_carries_all_three_lanes(self) -> None:
        b = _bundle()
        assert len(b.vendor_bills) == 6
        assert len(b.open_jobs) == 5
        assert len(b.installed_equipment) == 4
        # core filing lane still populated (no regression)
        assert len(b.documents) == 12

    def test_ap_lane_oracle(self) -> None:
        # 6 bills: 3 clean printed matches (JOB-9001/9002/9003) auto-propose; handwritten + missing +
        # unknown-job# (JOB-9999) -> 3 need a human.
        _, ap, _ = _analyses()
        assert (ap.totals.bills_processed, ap.totals.auto_proposed, ap.totals.needs_human) == (6, 3, 3)
        assert ap.totals.auto_value_cents == 184500 + 96200 + 412000  # 692,700¢
        assert {d.bill_id for d in ap.drafts} == {"BILL-5001", "BILL-5002", "BILL-5003"}

    def test_warranty_lane_oracle(self) -> None:
        # 4 equipment: Fujitsu + Mitsubishi + Daikin with serials -> 3 packets; Fujitsu w/ null serial
        # -> 1 needs-human.
        _, _, wr = _analyses()
        assert (wr.totals.equipment_processed, wr.totals.packets_ready, wr.totals.needs_human) == (4, 3, 1)
        assert {x.equipment_id for x in wr.needs_human} == {"EQ-3004"}  # unreadable serial


class TestServiceRows:
    def test_recommendation_rows_include_both_lanes(self) -> None:
        docs, ap, wr = _analyses()
        rows = _recommendation_rows(docs, ap, wr)
        kinds = {r["kind"] for r in rows}
        assert {"ap_draft", "ap_needs_human", "warranty_packet", "warranty_needs_human"} <= kinds
        ap_draft_rows = [r for r in rows if r["kind"] == "ap_draft"]
        assert len(ap_draft_rows) == 3
        # economic impact carried in cents on AP rows
        assert all(r["economic_impact_cents"] for r in ap_draft_rows)

    def test_reasoning_summary_carries_lane_counts(self) -> None:
        docs, ap, wr = _analyses()
        summary = dict(_reasoning_rows(docs, ap, wr, "template"))["analyze:summary"]
        assert "ap_auto=3" in summary
        assert "warranty_packets=3" in summary


class TestResultSchema:
    def test_build_result_surfaces_sections(self) -> None:
        docs, ap, wr = _analyses()
        result = build_result(
            docs, narrative="ok", analysis_timestamp=datetime.now(timezone.utc),
            ap_analysis=ap, warranty_analysis=wr,
        )
        assert result.accounts_payable is not None
        assert result.accounts_payable.totals.auto_proposed == 3
        assert result.accounts_payable.totals.auto_value_usd == 6927.00
        assert result.warranty is not None
        assert result.warranty.totals.packets_ready == 3
        # a warranty packet's required fields are filled
        fuj = next(p for p in result.warranty.packets if p.brand == "Fujitsu")
        assert fuj.fields["serial_number"] == "FJ26-0001188"

    def test_build_result_without_lanes_is_backward_compatible(self) -> None:
        docs, _, _ = _analyses()
        result = build_result(docs, narrative="ok", analysis_timestamp=datetime.now(timezone.utc))
        assert result.accounts_payable is None and result.warranty is None
