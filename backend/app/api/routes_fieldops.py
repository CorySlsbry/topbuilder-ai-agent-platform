"""Field-ops endpoints — the technician's mobile surface: jobs, pricebook, and the custom-quote builder."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.actions.schemas import ActionOut
from app.api.deps import get_principal
from app.fieldops import service
from app.fieldops.margin import MarginQuoteResult, gross_margin_pct
from app.fieldops.models import QuoteLineItem
from app.fieldops.quote import QuoteError, QuoteResult
from app.security import Principal

router = APIRouter(prefix="/v1/field", tags=["fieldops"])


def _usd(cents: int) -> float:
    return round(cents / 100, 2)


def _fmt(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h:02d}:{m:02d}"


class PricebookServiceOut(BaseModel):
    code: str
    name: str
    category: str
    unit_price_usd: float
    taxable: bool


class FieldJobOut(BaseModel):
    id: str
    customer_name: str
    trade: str
    job_type: str
    required_skill: str
    window: str
    status: str


class QuoteLineItemIn(BaseModel):
    service_code: str
    qty: int = 1


class QuoteRequestIn(BaseModel):
    line_items: list[QuoteLineItemIn] = Field(default_factory=list)
    tax_rate: float | None = None
    job_ref: str | None = None


class PricedLineOut(BaseModel):
    service_code: str
    name: str
    qty: int
    unit_price_usd: float
    line_total_usd: float
    taxable: bool


class QuoteResultOut(BaseModel):
    lines: list[PricedLineOut]
    subtotal_usd: float
    taxable_subtotal_usd: float
    tax_rate: float
    tax_usd: float
    total_usd: float


def _quote_out(q: QuoteResult) -> QuoteResultOut:
    return QuoteResultOut(
        lines=[
            PricedLineOut(
                service_code=line.service_code, name=line.name, qty=line.qty,
                unit_price_usd=_usd(line.unit_price_cents), line_total_usd=_usd(line.line_total_cents),
                taxable=line.taxable,
            )
            for line in q.lines
        ],
        subtotal_usd=_usd(q.subtotal_cents),
        taxable_subtotal_usd=_usd(q.taxable_subtotal_cents),
        tax_rate=q.tax_rate,
        tax_usd=_usd(q.tax_cents),
        total_usd=_usd(q.total_cents),
    )


@router.get("/pricebook", response_model=list[PricebookServiceOut])
async def pricebook(principal: Principal = Depends(get_principal)) -> list[PricebookServiceOut]:
    return [
        PricebookServiceOut(
            code=s.code, name=s.name, category=s.category,
            unit_price_usd=_usd(s.unit_price_cents), taxable=s.taxable,
        )
        for s in service.load_pricebook()
    ]


@router.get("/jobs", response_model=list[FieldJobOut])
async def jobs(principal: Principal = Depends(get_principal)) -> list[FieldJobOut]:
    return [
        FieldJobOut(
            id=j.id, customer_name=j.customer_name, trade=j.trade, job_type=j.job_type,
            required_skill=j.required_skill,
            window=f"{_fmt(j.window_start_min)}-{_fmt(j.window_end_min)}", status=j.status,
        )
        for j in await service.get_jobs(date.today())
    ]


@router.post("/quote", response_model=QuoteResultOut)
async def quote(req: QuoteRequestIn, principal: Principal = Depends(get_principal)) -> QuoteResultOut:
    """Price the tech's current service selection — add/remove on the phone, see the live total."""
    items = [QuoteLineItem(service_code=i.service_code, qty=i.qty) for i in req.line_items]
    try:
        return _quote_out(service.build_quote(items, req.tax_rate))
    except QuoteError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/quote/submit", response_model=ActionOut, status_code=status.HTTP_201_CREATED)
async def submit_quote(req: QuoteRequestIn, principal: Principal = Depends(get_principal)) -> ActionOut:
    """Submit the built quote as a ServiceTitan estimate — proposes a `create_estimate` action (HITL/auto)."""
    items = [QuoteLineItem(service_code=i.service_code, qty=i.qty) for i in req.line_items]
    try:
        return await service.submit_quote(principal, job_ref=req.job_ref, line_items=items, tax_rate=req.tax_rate)
    except QuoteError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# --------------------------------------------------------------------------------------------
# Equipment-driven MARGIN quote builder (gap B4 — "sell the company, not the box")
# --------------------------------------------------------------------------------------------
class CatalogItemOut(BaseModel):
    code: str
    name: str
    kind: str
    category: str
    brand: str
    cost_usd: float
    price_usd: float
    margin_pct: float
    sold_hours: float
    target_margin_pct: float | None


class MarginLineIn(BaseModel):
    code: str
    qty: int = 1
    target_margin_pct: float | None = None


class MarginQuoteRequestIn(BaseModel):
    lines: list[MarginLineIn] = Field(default_factory=list)
    target_margin_pct: float = 45.0
    sqft: int | None = None
    avg_price_per_sqft_usd: float | None = None


class PricedMarginLineOut(BaseModel):
    code: str
    name: str
    kind: str
    brand: str
    qty: int
    sold_hours: float
    unit_price_usd: float
    unit_cost_usd: float
    line_price_usd: float
    line_cost_usd: float
    margin_pct: float
    target_margin_pct: float
    below_target: bool
    flags: list[str]


class MarginFlagOut(BaseModel):
    code: str
    line_name: str
    message: str


class MarginQuoteResultOut(BaseModel):
    lines: list[PricedMarginLineOut]
    total_price_usd: float
    total_cost_usd: float
    gross_profit_usd: float
    blended_margin_pct: float
    target_margin_pct: float
    total_sold_hours: float
    sqft: int | None
    sqft_price_per_unit_usd: float | None
    benchmark_price_usd: float | None
    flags: list[MarginFlagOut]
    has_blocking_flag: bool


def _margin_out(r: MarginQuoteResult) -> MarginQuoteResultOut:
    return MarginQuoteResultOut(
        lines=[
            PricedMarginLineOut(
                code=line.code, name=line.name, kind=line.kind, brand=line.brand, qty=line.qty,
                sold_hours=line.sold_hours,
                unit_price_usd=_usd(line.unit_price_cents), unit_cost_usd=_usd(line.unit_cost_cents),
                line_price_usd=_usd(line.line_price_cents), line_cost_usd=_usd(line.line_cost_cents),
                margin_pct=line.margin_pct, target_margin_pct=line.target_margin_pct,
                below_target=line.below_target, flags=line.flags,
            )
            for line in r.lines
        ],
        total_price_usd=_usd(r.total_price_cents),
        total_cost_usd=_usd(r.total_cost_cents),
        gross_profit_usd=_usd(r.gross_profit_cents),
        blended_margin_pct=r.blended_margin_pct,
        target_margin_pct=r.target_margin_pct,
        total_sold_hours=r.total_sold_hours,
        sqft=r.sqft,
        sqft_price_per_unit_usd=None if r.sqft_price_per_unit_cents is None else _usd(r.sqft_price_per_unit_cents),
        benchmark_price_usd=None if r.benchmark_price_cents is None else _usd(r.benchmark_price_cents),
        flags=[MarginFlagOut(code=f.code, line_name=f.line_name, message=f.message) for f in r.flags],
        has_blocking_flag=r.has_blocking_flag,
    )


@router.get("/catalog", response_model=list[CatalogItemOut])
async def catalog(principal: Principal = Depends(get_principal)) -> list[CatalogItemOut]:
    """Equipment + labor + materials for the margin quote builder (cost is shown to the tech here)."""
    return [
        CatalogItemOut(
            code=c.code, name=c.name, kind=c.kind, category=c.category, brand=c.brand,
            cost_usd=_usd(c.cost_cents), price_usd=_usd(c.price_cents),
            margin_pct=gross_margin_pct(c.price_cents, c.cost_cents),
            sold_hours=c.sold_hours, target_margin_pct=c.target_margin_pct,
        )
        for c in service.load_margin_catalog()
    ]


@router.post("/quote/margin", response_model=MarginQuoteResultOut)
async def margin_quote(
    req: MarginQuoteRequestIn, principal: Principal = Depends(get_principal)
) -> MarginQuoteResultOut:
    """Price the equipment-driven quote and surface the BLENDED margin + the red leak flags.

    Equipment-driven: each line carries cost, sold-hours, and a target margin; true gross margin =
    (price - cost)/price. Flags the low-margin / premium-brand-low-margin / excess-material misses and
    cross-checks against the average $/sqft benchmark — so the tech sees the margin before sending.
    """
    requested = [
        service.MarginLineRequest(code=i.code, qty=i.qty, target_margin_pct=i.target_margin_pct)
        for i in req.lines
    ]
    sqft_cents = None if req.avg_price_per_sqft_usd is None else round(req.avg_price_per_sqft_usd * 100)
    try:
        return _margin_out(
            service.build_margin_quote(
                requested,
                target_margin_pct=req.target_margin_pct,
                sqft=req.sqft,
                avg_price_per_sqft_cents=sqft_cents,
            )
        )
    except QuoteError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
