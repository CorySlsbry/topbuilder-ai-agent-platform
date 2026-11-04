"""Domain models for the Financial Forecasting agent (dependency-free, stdlib only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Job:
    id: str
    name: str
    customer_segment: str
    status: str
    contract_value: float
    budgeted_cost: float
    actual_cost_to_date: float
    percent_complete: float  # 0..1
    billed_to_date: float


@dataclass(frozen=True)
class ARInvoice:
    id: str
    customer_segment: str
    amount: float
    issued: date
    due: date
    paid: bool = False


@dataclass(frozen=True)
class APBill:
    id: str
    vendor: str
    amount: float
    due: date
    paid: bool = False


@dataclass(frozen=True)
class PaymentVelocity:
    customer_segment: str
    avg_days_to_pay: float
    sample_size: int


@dataclass(frozen=True)
class CompanyFinancials:
    starting_cash: float
    target_gross_margin: float


@dataclass(frozen=True)
class FinancialData:
    as_of: date
    starting_cash: float
    target_gross_margin: float  # e.g. 0.35
    jobs: list[Job]
    ar_invoices: list[ARInvoice]
    ap_bills: list[APBill]
    payment_velocity: list[PaymentVelocity] = field(default_factory=list)
