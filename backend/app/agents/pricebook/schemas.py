"""API-facing schemas (spec-shaped) + mapper for the Pricebook agent.

Every dollar figure derives from the deterministic engine's *cents* (ADR 0003); this layer formats to
dollars and rolls up. The headline metric is the net repricing impact (``total_price_delta_usd``) and the
count of items flagged beyond tolerance for human review.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.agents.pricebook.analytics import PricebookAnalysis


def _usd(cents: int) -> float:
    return round(cents / 100, 2)


class MaterialLineChangeOut(BaseModel):
    sku: str
    qty: float
    old_unit_cost_usd: float
    new_unit_cost_usd: float
    old_line_cost_usd: float
    new_line_cost_usd: float
    vendor: str | None


class PricebookItemChangeOut(BaseModel):
    code: str
    name: str
    category: str
    sold_hours: float
    sold_hour_rate_usd: float
    markup_pct: float
    labor_cost_usd: float
    old_materials_cost_usd: float
    new_materials_cost_usd: float
    materials_delta_usd: float
    old_price_usd: float
    new_price_usd: float
    price_delta_usd: float
    price_delta_pct: float
    old_margin_usd: float
    new_margin_usd: float
    margin_delta_usd: float
    changed_skus: list[str]
    beyond_tolerance: bool
    lines: list[MaterialLineChangeOut]


class PricebookTotalsOut(BaseModel):
    items: int
    items_affected: int
    items_flagged: int
    total_price_delta_usd: float
    distinct_skus: int
    skus_updated: int
    vendor_coverage_pct: float
    avg_markup_pct: float


class PricebookRunResult(BaseModel):
    run_id: uuid.UUID | None = None
    agent: str = "pricebook"
    source_system: str = "ServiceTitan"  # the Pricebook lives in ServiceTitan
    analysis_timestamp: datetime
    as_of: str
    tolerance_pct: float
    changes: list[PricebookItemChangeOut]
    totals: PricebookTotalsOut
    reasoning_logs: str
    inputs_hash: str


def build_result(
    analysis: PricebookAnalysis,
    *,
    narrative: str,
    analysis_timestamp: datetime,
    run_id: uuid.UUID | None = None,
    source_system: str = "ServiceTitan",
) -> PricebookRunResult:
    changes = [
        PricebookItemChangeOut(
            code=c.code,
            name=c.name,
            category=c.category,
            sold_hours=c.sold_hours,
            sold_hour_rate_usd=_usd(c.sold_hour_rate_cents),
            markup_pct=c.markup_pct,
            labor_cost_usd=_usd(c.labor_cost_cents),
            old_materials_cost_usd=_usd(c.old_materials_cost_cents),
            new_materials_cost_usd=_usd(c.new_materials_cost_cents),
            materials_delta_usd=_usd(c.materials_delta_cents),
            old_price_usd=_usd(c.old_price_cents),
            new_price_usd=_usd(c.new_price_cents),
            price_delta_usd=_usd(c.price_delta_cents),
            price_delta_pct=c.price_delta_pct,
            old_margin_usd=_usd(c.old_margin_cents),
            new_margin_usd=_usd(c.new_margin_cents),
            margin_delta_usd=_usd(c.margin_delta_cents),
            changed_skus=c.changed_skus,
            beyond_tolerance=c.beyond_tolerance,
            lines=[
                MaterialLineChangeOut(
                    sku=line.sku,
                    qty=line.qty,
                    old_unit_cost_usd=_usd(line.old_unit_cost_cents),
                    new_unit_cost_usd=_usd(line.new_unit_cost_cents),
                    old_line_cost_usd=_usd(line.old_line_cost_cents),
                    new_line_cost_usd=_usd(line.new_line_cost_cents),
                    vendor=line.vendor,
                )
                for line in c.lines
            ],
        )
        for c in analysis.changes
    ]
    t = analysis.totals
    totals = PricebookTotalsOut(
        items=t.items,
        items_affected=t.items_affected,
        items_flagged=t.items_flagged,
        total_price_delta_usd=_usd(t.total_price_delta_cents),
        distinct_skus=t.distinct_skus,
        skus_updated=t.skus_updated,
        vendor_coverage_pct=t.vendor_coverage_pct,
        avg_markup_pct=t.avg_markup_pct,
    )
    return PricebookRunResult(
        run_id=run_id,
        source_system=source_system,
        analysis_timestamp=analysis_timestamp,
        as_of=analysis.as_of.isoformat(),
        tolerance_pct=analysis.tolerance_pct,
        changes=changes,
        totals=totals,
        reasoning_logs=narrative,
        inputs_hash=analysis.inputs_hash,
    )
