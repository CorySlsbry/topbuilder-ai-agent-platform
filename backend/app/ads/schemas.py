"""Engine CONTRACT for the Admin Ads-CRM (ADR 0009).

These Pydantic v2 models are the FINAL, frozen interface between the pure deterministic ad-engine
(``app/ads/engine.py``) and everything downstream — the ad agent, the action executors, the routes.
Downstream code imports these; keep them clean and stable.

POSTURE (load-bearing):
  * Money is integer CENTS everywhere in OUR domain. The per-platform ``requests`` payloads carry the
    money already converted to the PLATFORM's own unit, computed deterministically by the engine —
    Meta wants the daily budget in cents *as a string*; Google wants ``amount_micros = cents * 10_000``.
  * Every create payload is built PAUSED-on-create (ADR 0007 — nothing goes live without the human
    approve→execute step). The engine never performs a write; it only assembles the request dicts.
  * The LLM never computes any figure in here (ADR 0003) — every number is pure code.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GeoPoint(BaseModel):
    """A single geo-target: a circle of ``radius_mi`` miles around a lat/long."""

    latitude: float
    longitude: float
    radius_mi: float


class GeoSpec(BaseModel):
    """The geographic targeting for a campaign (custom radius locations)."""

    custom_locations: list[GeoPoint] = Field(default_factory=list)
    # how a person relates to the area: 'recent' (recently in), 'home', 'travel_in' — Meta's location_types.
    location_type: str = "recent"


class BudgetPlan(BaseModel):
    """Spend plan in integer cents (our canonical money unit)."""

    daily_cents: int
    lifetime_cap_cents: int


class SchedulePlan(BaseModel):
    """The flight window. ``start_at`` < ``end_at`` is enforced by the engine, not here."""

    start_at: datetime
    end_at: datetime
    tz: str


class CreativePlan(BaseModel):
    """The ad creative copy + landing destination."""

    headline: str
    primary_text: str
    description: str
    landing_url: str
    image_ref: str | None = None


class CampaignPlan(BaseModel):
    """The fully-resolved, platform-ready campaign plan — the engine's single output type.

    ``requests`` holds the platform-specific CREATE payload dicts, all PAUSED-on-create, with money
    already in the platform's own units:
      * meta:   keys ``campaign`` / ``adset`` / ``adcreative`` / ``ad``
      * google: keys ``campaign_budget`` / ``campaign`` / ``ad_group`` / ``criterion`` / ``ad``
    """

    platform: str  # 'meta' | 'google'
    name: str
    objective: str
    budget: BudgetPlan
    schedule: SchedulePlan
    geo: GeoSpec
    creative: CreativePlan
    targeting: dict = Field(default_factory=dict)
    requests: dict = Field(default_factory=dict)
