"""Unit tests for the ServiceTitan payroll-adjustment request-builder (pure mapping, ADR 0003/0005).

Each asserted field is an independent oracle: a representative payroll-gap adjustment is mapped, and we
verify the path + every body field by hand. The load-bearing invariant is that ``hours`` carries the
VERIFIED CLOCK hours (``computed_hours``), never the unverified ``claimed_hours``, and that the memo
quotes the gap.
"""
from __future__ import annotations

import pytest

from app.actions.executors import ActionError
from app.integrations.servicetitan.payroll_writeback import (
    DEFAULT_ADJUSTMENT_TYPE,
    TENANT_PLACEHOLDER,
    build_payroll_adjustment_request,
)

# Representative adjustment: a technician claimed 16h on the pay form, but the dispatch->completion clock
# shows 12.5h -> a +3.5h gap. The verified CLOCK hours (12.5) are what get posted, not the 16.
_REP_PARAMS = {
    "st_tenant_id": "9876543210",
    "worker_id": "tech-204",
    "worker_name": "Sam R.",
    "period_start": "2026-06-01",
    "period_end": "2026-06-14",
    "claimed_hours": 16.0,
    "computed_hours": 12.5,
    "hours_discrepancy": 3.5,
}


class TestBuildPayrollAdjustmentRequest:
    def test_path_uses_tenant_id(self) -> None:
        path, _ = build_payroll_adjustment_request(_REP_PARAMS)
        assert path == "/payroll/v2/tenant/9876543210/payroll-adjustments"

    def test_employee_id_maps_from_worker_id(self) -> None:
        _, body = build_payroll_adjustment_request(_REP_PARAMS)
        assert body["employeeId"] == "tech-204"

    def test_posted_on_is_period_end(self) -> None:
        _, body = build_payroll_adjustment_request(_REP_PARAMS)
        assert body["postedOn"] == "2026-06-14"

    def test_hours_are_computed_clock_hours_not_claimed(self) -> None:
        # The whole point of the gap review: pay the verified clock (12.5), never the claimed (16.0).
        _, body = build_payroll_adjustment_request(_REP_PARAMS)
        assert body["hours"] == 12.5
        assert body["hours"] != _REP_PARAMS["claimed_hours"]

    def test_default_adjustment_type(self) -> None:
        _, body = build_payroll_adjustment_request(_REP_PARAMS)
        assert body["payrollAdjustmentType"] == DEFAULT_ADJUSTMENT_TYPE == "ManualAdjustment"

    def test_memo_quotes_the_gap(self) -> None:
        _, body = build_payroll_adjustment_request(_REP_PARAMS)
        memo = body["memo"]
        assert "Sam R." in memo
        assert "12.5h" in memo  # the posted (clock) hours
        assert "16h" in memo  # the claimed pay-form hours
        assert "+3.5h" in memo  # the signed gap

    def test_optional_fields_omitted_when_absent(self) -> None:
        _, body = build_payroll_adjustment_request(_REP_PARAMS)
        assert "amount" not in body
        assert "activityCodeId" not in body
        assert "invoiceId" not in body
        assert "jobId" not in body

    def test_optional_fields_mapped_when_present(self) -> None:
        params = {
            **_REP_PARAMS,
            "amount_cents": 12345,  # -> $123.45
            "activity_code_id": "AC-7",
            "payroll_adjustment_type": "OvertimeCorrection",
            "invoice_id": "INV-55",
            "job_id": "JOB-99",
        }
        _, body = build_payroll_adjustment_request(params)
        assert body["amount"] == 123.45
        assert body["activityCodeId"] == "AC-7"
        assert body["payrollAdjustmentType"] == "OvertimeCorrection"
        assert body["invoiceId"] == "INV-55"
        assert body["jobId"] == "JOB-99"

    def test_full_representative_request(self) -> None:
        path, body = build_payroll_adjustment_request(_REP_PARAMS)
        assert path == "/payroll/v2/tenant/9876543210/payroll-adjustments"
        assert body == {
            "employeeId": "tech-204",
            "postedOn": "2026-06-14",
            "hours": 12.5,
            "payrollAdjustmentType": "ManualAdjustment",
            "memo": (
                "Payroll adjustment for Sam R.: posting verified clock hours 12.5h "
                "(pay-form claimed 16h, gap +3.5h) — reviewed against dispatch->completion clock "
                "before posting."
            ),
        }

    def test_tenant_placeholder_when_missing(self) -> None:
        params = {k: v for k, v in _REP_PARAMS.items() if k != "st_tenant_id"}
        path, _ = build_payroll_adjustment_request(params)
        assert path == f"/payroll/v2/tenant/{TENANT_PLACEHOLDER}/payroll-adjustments"

    def test_missing_worker_id_raises(self) -> None:
        params = {k: v for k, v in _REP_PARAMS.items() if k != "worker_id"}
        with pytest.raises(ActionError):
            build_payroll_adjustment_request(params)
