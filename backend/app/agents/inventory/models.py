"""Domain models for the Inventory & Supply Chain agent (dependency-free, stdlib only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Part:
    sku: str
    name: str
    category: str
    unit_cost: float
    billable_price: float
    margin_class: str  # high | standard


@dataclass(frozen=True)
class ReorderState:
    sku: str
    on_hand: float
    avg_daily_usage: float
    lead_time_days: float
    safety_stock: float
    current_reorder_point: float
    usage_sample_days: int


@dataclass(frozen=True)
class TruckStockCount:
    technician_id: str
    sku: str
    expected_qty: float
    counted_qty: float


@dataclass(frozen=True)
class MaterialUsage:
    job_id: str
    sku: str
    qty_used: float
    billed: bool


@dataclass(frozen=True)
class VendorQuote:
    sku: str
    vendor: str
    unit_price: float
    lead_time_days: float


@dataclass(frozen=True)
class InventoryData:
    as_of: date
    parts: list[Part]
    reorder_state: list[ReorderState]
    truck_stock: list[TruckStockCount]
    material_usage: list[MaterialUsage]
    vendor_quotes: list[VendorQuote] = field(default_factory=list)
