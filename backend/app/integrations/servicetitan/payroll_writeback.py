"""Pure request-builder for the ServiceTitan payroll-adjustment write-back.

Maps our canonical payroll-gap fields (the claimed-vs-clocked review the Workforce agent surfaces, see
``app/agents/workforce/payroll.py``) onto ServiceTitan's Payroll API *adjustment* shape, returning the
``(path, body)`` an authenticated client would POST. It is pure, stdlib-only, and deterministic
(ADR 0003): no HTTP, no clock, no randomness — identical inputs always yield the identical request, so
the mapping itself is unit-testable independent of any live tenant.

The actual HTTP send stays FAIL-CLOSED (ADR 0005): the live executor branch builds the request via this
module (proving the mapping is correct) and then raises until the write is verified against a real
tenant — it never POSTs and never fabricates a success. Exact ST field names should be confirmed against
a live tenant; the transformation logic is what is tested here.

The load-bearing field is ``hours``: it carries the VERIFIED CLOCK hours (``computed_hours``), never the
technician's unverified self-reported ``claimed_hours`` — that gap is the whole reason the adjustment
goes through human review (Alex discovery, 2026-06-16).
"""
from __future__ import annotations

from app.actions.executors import ActionError

# ServiceTitan Payroll API adjustment endpoint. ``{tenant}`` is the ST tenant id.
PAYROLL_ADJUSTMENTS_PATH = "/payroll/v2/tenant/{tenant}/payroll-adjustments"

# Used in the path when no tenant id is supplied — a clear placeholder, never a silent default that
# could write to the wrong tenant.
TENANT_PLACEHOLDER = "UNKNOWN_TENANT"

# ServiceTitan adjustment type when the caller doesn't specify one. A manual, clerk-reviewed correction
# of pay-form hours against the clock is a manual adjustment.
DEFAULT_ADJUSTMENT_TYPE = "ManualAdjustment"


def _gap_memo(params: dict, hours: float) -> str:
    """Human-readable note quoting the claimed-vs-computed gap, for the payroll clerk's audit trail."""
    name = params.get("worker_name") or params.get("worker_id")
    claimed = params.get("claimed_hours")
    discrepancy = params.get("hours_discrepancy")
    note = (
        f"Payroll adjustment for {name}: posting verified clock hours {hours:g}h"
    )
    if claimed is not None:
        note += f" (pay-form claimed {float(claimed):g}h"
        if discrepancy is not None:
            note += f", gap {float(discrepancy):+g}h"
        note += ")"
    note += " — reviewed against dispatch->completion clock before posting."
    return note


def build_payroll_adjustment_request(params: dict) -> tuple[str, dict]:
    """Build the ``(path, body)`` for a ServiceTitan payroll-adjustment write.

    Maps our canonical fields to ServiceTitan's:

      * ``employeeId``            <- ``worker_id``        (required; ``ActionError`` if missing)
      * ``postedOn``              <- ``period_end``       (ISO date the adjustment posts on)
      * ``hours``                 <- ``computed_hours``   (the VERIFIED clock hours, NOT ``claimed_hours``)
      * ``amount``                <- ``amount_cents``/100 (optional dollar amount; integer cents in)
      * ``payrollAdjustmentType`` <- ``payroll_adjustment_type`` (default ``ManualAdjustment``)
      * ``activityCodeId``        <- ``activity_code_id`` (optional)
      * ``invoiceId`` / ``jobId`` <- optional passthrough
      * ``memo``                  <- a generated note quoting the claimed-vs-computed gap

    Only fields that are present are included (no ``None`` keys leak into the request), except the always-
    present ``employeeId``/``postedOn``/``hours``/``payrollAdjustmentType``/``memo``.
    """
    worker_id = params.get("worker_id")
    if not worker_id:
        raise ActionError("build_payroll_adjustment_request requires 'worker_id'")

    tenant = params.get("st_tenant_id") or TENANT_PLACEHOLDER
    path = PAYROLL_ADJUSTMENTS_PATH.format(tenant=tenant)

    # Pay is always from the clock: the verified COMPUTED hours, never the unverified CLAIMED hours.
    hours = float(params.get("computed_hours") or 0.0)

    body: dict = {
        "employeeId": str(worker_id),
        "postedOn": params.get("period_end"),
        "hours": hours,
        "payrollAdjustmentType": params.get("payroll_adjustment_type") or DEFAULT_ADJUSTMENT_TYPE,
        "memo": _gap_memo(params, hours),
    }

    amount_cents = params.get("amount_cents")
    if amount_cents is not None:
        body["amount"] = round(int(amount_cents) / 100, 2)

    # Optional passthrough fields — included only when present.
    activity_code_id = params.get("activity_code_id")
    if activity_code_id is not None:
        body["activityCodeId"] = activity_code_id
    invoice_id = params.get("invoice_id")
    if invoice_id is not None:
        body["invoiceId"] = invoice_id
    job_id = params.get("job_id")
    if job_id is not None:
        body["jobId"] = job_id

    return path, body
