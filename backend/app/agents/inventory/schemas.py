"""API-facing schemas (spec-shaped) + mapper for the Inventory agent."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.agents.inventory.analytics import InventoryAnalysis
from app.agents.inventory.proration import ConsumableProrationAnalysis


class ReorderOut(BaseModel):
    sku: str
    name: str
    on_hand: float
    avg_daily_usage: float
    lead_time_days: float
    dynamic_reorder_point: float
    days_to_stockout: float | None
    recommended_order_qty: int
    stockout_exposure_usd: float
    margin_class: str
    confidence: float
    reasoning: str


class ShrinkageOut(BaseModel):
    technician_id: str
    sku: str
    name: str
    expected_qty: float
    counted_qty: float
    variance: float
    shrinkage_value_usd: float
    confidence: float
    reasoning: str


class UnbilledOut(BaseModel):
    job_id: str
    sku: str
    name: str
    qty_used: float
    unbilled_value_usd: float
    reasoning: str


class ArbitrageOut(BaseModel):
    sku: str
    name: str
    current_unit_cost: float
    best_vendor: str
    best_unit_price: float
    annual_savings_usd: float
    reasoning: str


class InventoryTotals(BaseModel):
    reorders_count: int
    total_stockout_exposure_usd: float
    total_shrinkage_usd: float
    total_unbilled_usd: float
    total_arbitrage_annual_usd: float


class InventoryRunResult(BaseModel):
    run_id: uuid.UUID | None = None
    agent: str = "inventory"
    source_system: str = "ServiceTitan"  # the tenant's field-service system of record (fsm_provider)
    analysis_timestamp: datetime
    as_of: date
    critical_reorders: list[ReorderOut]
    shrinkage_alerts: list[ShrinkageOut]
    unbilled_materials: list[UnbilledOut]
    vendor_arbitrage: list[ArbitrageOut]
    totals: InventoryTotals
    reasoning_logs: str
    inputs_hash: str


# --------------------------------------------------------------------------------------------
# Partial-consumable proration (Alex's metal-spool / copper-coil pain)
# --------------------------------------------------------------------------------------------
class JobAllocationOut(BaseModel):
    job_id: str
    allocated_cost_usd: float
    usage_proxy: float | None
    share_pct: float
    reasoning: str


class LotProrationOut(BaseModel):
    sku: str
    name: str
    unit: str
    method: str
    total_cost_usd: float
    total_quantity: float
    job_count: int
    dump_job_id: str
    miscost_corrected_usd: float
    allocations: list[JobAllocationOut]
    reasoning: str
    inputs_hash: str


class ProrationTotals(BaseModel):
    lots_count: int
    total_prorated_usd: float
    total_miscost_corrected_usd: float


class ConsumableProrationResult(BaseModel):
    run_id: uuid.UUID | None = None
    agent: str = "inventory"
    source_system: str = "ServiceTitan"
    analysis_timestamp: datetime
    as_of: date
    lots: list[LotProrationOut]
    totals: ProrationTotals
    reasoning_logs: str
    inputs_hash: str


def build_proration_result(
    analysis: ConsumableProrationAnalysis,
    *,
    narrative: str,
    analysis_timestamp: datetime,
    run_id: uuid.UUID | None = None,
    source_system: str = "ServiceTitan",
) -> ConsumableProrationResult:
    lots = [
        LotProrationOut(
            sku=l.sku, name=l.name, unit=l.unit, method=l.method,
            total_cost_usd=round(l.total_cost_cents / 100, 2),
            total_quantity=l.total_quantity, job_count=l.job_count,
            dump_job_id=l.dump_job_id,
            miscost_corrected_usd=round(l.miscost_corrected_cents / 100, 2),
            allocations=[
                JobAllocationOut(
                    job_id=a.job_id,
                    allocated_cost_usd=round(a.allocated_cost_cents / 100, 2),
                    usage_proxy=a.usage_proxy, share_pct=a.share_pct, reasoning=a.reasoning,
                )
                for a in l.allocations
            ],
            reasoning=l.reasoning, inputs_hash=l.inputs_hash,
        )
        for l in analysis.lots
    ]
    totals = ProrationTotals(
        lots_count=len(lots),
        total_prorated_usd=round(analysis.total_prorated_cents / 100, 2),
        total_miscost_corrected_usd=round(analysis.total_miscost_corrected_cents / 100, 2),
    )
    return ConsumableProrationResult(
        run_id=run_id, source_system=source_system, analysis_timestamp=analysis_timestamp,
        as_of=analysis.as_of, lots=lots, totals=totals, reasoning_logs=narrative,
        inputs_hash=analysis.inputs_hash,
    )


def build_result(
    analysis: InventoryAnalysis,
    *,
    narrative: str,
    analysis_timestamp: datetime,
    run_id: uuid.UUID | None = None,
    source_system: str = "ServiceTitan",
) -> InventoryRunResult:
    reorders = [
        ReorderOut(
            sku=r.sku, name=r.name, on_hand=r.on_hand, avg_daily_usage=r.avg_daily_usage,
            lead_time_days=r.lead_time_days, dynamic_reorder_point=r.dynamic_reorder_point,
            days_to_stockout=r.days_to_stockout, recommended_order_qty=r.recommended_order_qty,
            stockout_exposure_usd=round(r.stockout_exposure_cents / 100, 2),
            margin_class=r.margin_class, confidence=r.confidence, reasoning=r.reasoning,
        )
        for r in analysis.critical_reorders
    ]
    shrinkage = [
        ShrinkageOut(
            technician_id=s.technician_id, sku=s.sku, name=s.name, expected_qty=s.expected_qty,
            counted_qty=s.counted_qty, variance=s.variance,
            shrinkage_value_usd=round(s.shrinkage_value_cents / 100, 2),
            confidence=s.confidence, reasoning=s.reasoning,
        )
        for s in analysis.shrinkage_alerts
    ]
    unbilled = [
        UnbilledOut(
            job_id=u.job_id, sku=u.sku, name=u.name, qty_used=u.qty_used,
            unbilled_value_usd=round(u.unbilled_value_cents / 100, 2), reasoning=u.reasoning,
        )
        for u in analysis.unbilled_materials
    ]
    arbitrage = [
        ArbitrageOut(
            sku=o.sku, name=o.name, current_unit_cost=o.current_unit_cost,
            best_vendor=o.best_vendor, best_unit_price=o.best_unit_price,
            annual_savings_usd=round(o.annual_savings_cents / 100, 2), reasoning=o.reasoning,
        )
        for o in analysis.arbitrage
    ]
    totals = InventoryTotals(
        reorders_count=len(reorders),
        total_stockout_exposure_usd=round(sum(r.stockout_exposure_usd for r in reorders), 2),
        total_shrinkage_usd=round(sum(s.shrinkage_value_usd for s in shrinkage), 2),
        total_unbilled_usd=round(sum(u.unbilled_value_usd for u in unbilled), 2),
        total_arbitrage_annual_usd=round(sum(o.annual_savings_usd for o in arbitrage), 2),
    )
    return InventoryRunResult(
        run_id=run_id,
        source_system=source_system,
        analysis_timestamp=analysis_timestamp,
        as_of=analysis.as_of,
        critical_reorders=reorders,
        shrinkage_alerts=shrinkage,
        unbilled_materials=unbilled,
        vendor_arbitrage=arbitrage,
        totals=totals,
        reasoning_logs=narrative,
        inputs_hash=analysis.inputs_hash,
    )
