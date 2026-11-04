"""Pure tests for the Financial data assembler's best-effort lanes.

A live QBO client fails closed (ADR 0005) on the lanes not yet verified against a real company
(`get_jobs`, `get_payment_velocity`). The assembler must degrade those lanes to empty — mirroring
`agents/documents/data.py` — so a connected tenant still completes a run on the lanes that ARE
available (cash, AR, AP), instead of the whole run failing.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.agents.financial.data import assemble_financial_data
from app.agents.financial.models import APBill, ARInvoice, CompanyFinancials, Job, PaymentVelocity

AS_OF = date(2026, 6, 30)
AR = [ARInvoice(id="INV-1", customer_segment="commercial", amount=1200.0,
                issued=date(2026, 6, 1), due=date(2026, 7, 1))]
AP = [APBill(id="BILL-1", vendor="Ferguson", amount=412.5, due=date(2026, 7, 5))]


class QboLikeClient:
    """The live-QBO posture: core lanes mapped, jobs + velocity still fail-closed."""

    async def get_company_financials(self) -> CompanyFinancials:
        return CompanyFinancials(starting_cash=50_000.0, target_gross_margin=0.42)

    async def get_jobs(self) -> list[Job]:
        raise NotImplementedError("Map QBO Projects/job-costing -> Job (WIP fields).")

    async def get_ar_invoices(self) -> list[ARInvoice]:
        return AR

    async def get_ap_bills(self) -> list[APBill]:
        return AP

    async def get_payment_velocity(self) -> list[PaymentVelocity]:
        raise NotImplementedError("Compute PaymentVelocity from QBO payment history.")


class BrokenCoreClient(QboLikeClient):
    async def get_ar_invoices(self) -> list[ARInvoice]:
        raise NotImplementedError("core lanes are NOT best-effort")


async def test_unmapped_lanes_degrade_to_empty_and_the_run_completes() -> None:
    data = await assemble_financial_data(QboLikeClient(), as_of=AS_OF)

    assert data.as_of == AS_OF
    assert data.starting_cash == 50_000.0
    assert data.target_gross_margin == 0.42
    assert data.jobs == []              # fail-closed lane -> empty, never fabricated
    assert data.payment_velocity == []  # fail-closed lane -> empty, never fabricated
    assert data.ar_invoices == AR
    assert data.ap_bills == AP


async def test_core_lanes_still_fail_closed_not_best_effort() -> None:
    # AR/AP/company are the run's substance — an unmapped core lane must still raise (ADR 0005),
    # only the optional jobs/velocity lanes degrade.
    with pytest.raises(NotImplementedError):
        await assemble_financial_data(BrokenCoreClient(), as_of=AS_OF)
