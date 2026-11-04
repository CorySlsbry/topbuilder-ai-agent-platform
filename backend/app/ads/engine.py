"""Pure, deterministic ad-campaign engine (ADR 0003 — the LLM never computes a figure in here).

``build_from_template`` resolves the jsonb spec shapes stored on ``ad_campaign_templates`` (migration
0023) plus the selected ``ad_accounts`` row into a fully-platform-ready :class:`CampaignPlan`, including
the per-platform CREATE request payloads. There is NO I/O and NO DB access — every value is computed
from the inputs, so the whole module is unit-testable against hand-computed oracles.

Money is integer CENTS in our domain; the platform payloads carry money in the PLATFORM's own unit,
converted deterministically here:
  * Meta  — ``daily_budget`` is cents AS A STRING (Meta's "minor units" convention).
  * Google — ``amount_micros`` is ``cents * 10_000`` (1 currency unit = 1e6 micros; 1 cent = 1e4 micros).

Every create payload is built PAUSED (``status='PAUSED'``) — nothing goes live without the human
approve→execute step (ADR 0007). The engine assembles request dicts; it never performs a write.
"""
from __future__ import annotations

from datetime import datetime

from app.ads.schemas import (
    BudgetPlan,
    CampaignPlan,
    CreativePlan,
    GeoPoint,
    GeoSpec,
    SchedulePlan,
)

# 1 currency unit = 1_000_000 micros, and 1 unit = 100 cents, so 1 cent = 10_000 micros (Google Ads).
MICROS_PER_CENT = 10_000

_VALID_PLATFORMS = ("meta", "google")


# ── cents + schedule helpers (hand-checkable) ─────────────────────────────────────────────────────
def cents_to_micros(cents: int) -> int:
    """Google Ads money unit: ``amount_micros = cents * 10_000``."""
    return int(cents) * MICROS_PER_CENT


def cents_to_minor_unit_str(cents: int) -> str:
    """Meta money unit: the integer cents rendered as a string (Meta's API takes minor units as text)."""
    return str(int(cents))


def duration_days(schedule: SchedulePlan) -> int:
    """Whole-day length of the flight window (``end_at - start_at``, floored to days).

    Validates ``start_at < end_at`` first (a zero/negative window is a defect, not a 0-day campaign).
    """
    validate_window(schedule)
    return (schedule.end_at - schedule.start_at).days


def validate_window(schedule: SchedulePlan) -> None:
    """Raise ``ValueError`` unless the flight window is strictly start < end."""
    if schedule.start_at >= schedule.end_at:
        raise ValueError(
            f"schedule window must have start_at < end_at (got {schedule.start_at} >= {schedule.end_at})"
        )


# ── spend caps (executors call this BEFORE any spend write) ───────────────────────────────────────
def projected_lifetime_spend(daily_cents: int, lifetime_cap_cents: int) -> int:
    """The most a campaign can spend over its funded run: ``daily × floor(lifetime / daily)``.

    ``floor(lifetime / daily)`` is how many WHOLE days the lifetime cap funds at the daily rate; the
    run can't spend a partial day's budget on a day it can't afford. Raises ``ValueError`` if the daily
    budget is non-positive or already exceeds the whole lifetime cap (one day would blow the cap).
    """
    if daily_cents <= 0:
        raise ValueError("daily_cents must be positive to project lifetime spend")
    if daily_cents > lifetime_cap_cents:
        raise ValueError(
            f"daily spend {daily_cents}c exceeds the lifetime cap {lifetime_cap_cents}c "
            f"(one day would blow the lifetime budget)"
        )
    funded_days = lifetime_cap_cents // daily_cents
    return daily_cents * funded_days


def enforce_caps(daily_cents: int, lifetime_cap_cents: int, requested_daily_cents: int) -> None:
    """Refuse a spend that breaches the configured caps. Pure guard, raises ``ValueError`` on breach.

    Two independent checks (both hand-checkable):
      1. ``requested_daily_cents`` may not exceed the daily cap ``daily_cents``.
      2. The requested daily rate, run for its funded number of whole days against the LIFETIME cap,
         must itself be a coherent plan — a requested daily larger than the whole lifetime cap is
         rejected (it would blow the cap on day one). ``projected_lifetime_spend`` does this check on
         the requested rate.
    """
    if daily_cents <= 0:
        raise ValueError("daily_cents must be positive to project lifetime spend")
    if requested_daily_cents > daily_cents:
        raise ValueError(
            f"requested daily spend {requested_daily_cents}c exceeds the daily cap {daily_cents}c"
        )
    # Project the REQUESTED rate against the lifetime cap; raises if one requested day blows the cap.
    projected_lifetime_spend(requested_daily_cents, lifetime_cap_cents)


# ── spec resolvers (jsonb shapes from migration 0023 -> typed plans) ──────────────────────────────
def _resolve_geo(geo_spec: dict) -> GeoSpec:
    points = [
        GeoPoint(
            latitude=float(loc["lat"]),
            longitude=float(loc["long"]),
            radius_mi=float(loc.get("radius_mi", 1)),
        )
        for loc in geo_spec.get("custom_locations", [])
    ]
    return GeoSpec(custom_locations=points, location_type=geo_spec.get("location_type", "recent"))


def _resolve_budget(budget_spec: dict) -> BudgetPlan:
    return BudgetPlan(
        daily_cents=int(budget_spec.get("daily_cents", 0)),
        lifetime_cap_cents=int(budget_spec.get("lifetime_cap_cents", 0)),
    )


def _resolve_schedule(schedule_spec: dict) -> SchedulePlan:
    return SchedulePlan(
        start_at=_parse_dt(schedule_spec["start_at"]),
        end_at=_parse_dt(schedule_spec["end_at"]),
        tz=schedule_spec.get("tz", "UTC"),
    )


def _resolve_creative(creative_spec: dict) -> CreativePlan:
    return CreativePlan(
        headline=creative_spec.get("headline", ""),
        primary_text=creative_spec.get("primary_text", ""),
        description=creative_spec.get("description", ""),
        landing_url=creative_spec.get("landing_url", ""),
        image_ref=creative_spec.get("image_ref"),
    )


def _parse_dt(value: datetime | str) -> datetime:
    """Accept a datetime or an ISO-8601 string (the jsonb spec stores ISO strings)."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


# ── platform request builders ─────────────────────────────────────────────────────────────────────
def _meta_requests(
    *,
    name: str,
    objective: str,
    budget: BudgetPlan,
    schedule: SchedulePlan,
    geo: GeoSpec,
    creative: CreativePlan,
    targeting: dict,
    account_ref: str,
) -> dict:
    """Meta Marketing API CREATE payloads (campaign/adset/adcreative/ad), all PAUSED-on-create."""
    geo_targeting = {
        "geo_locations": {
            "location_types": [geo.location_type],
            "custom_locations": [
                {"latitude": p.latitude, "longitude": p.longitude, "radius": p.radius_mi, "distance_unit": "mile"}
                for p in geo.custom_locations
            ],
        },
        **targeting,
    }
    return {
        "campaign": {
            "name": name,
            "objective": objective,
            "status": "PAUSED",
            "special_ad_categories": [],
        },
        "adset": {
            "name": f"{name} — adset",
            "status": "PAUSED",
            "daily_budget": cents_to_minor_unit_str(budget.daily_cents),
            "lifetime_budget": cents_to_minor_unit_str(budget.lifetime_cap_cents),
            "start_time": schedule.start_at.isoformat(),
            "end_time": schedule.end_at.isoformat(),
            "targeting": geo_targeting,
            "billing_event": "IMPRESSIONS",
        },
        "adcreative": {
            "name": f"{name} — creative",
            "title": creative.headline,
            "body": creative.primary_text,
            "link_description": creative.description,
            "object_url": creative.landing_url,
            "image_ref": creative.image_ref,
        },
        "ad": {
            "name": f"{name} — ad",
            "status": "PAUSED",
            "account_ref": account_ref,
        },
    }


def _google_requests(
    *,
    name: str,
    objective: str,
    budget: BudgetPlan,
    schedule: SchedulePlan,
    geo: GeoSpec,
    creative: CreativePlan,
    targeting: dict,
    account_ref: str,
) -> dict:
    """Google Ads API CREATE payloads (campaign_budget/campaign/ad_group/criterion/ad), PAUSED."""
    return {
        "campaign_budget": {
            "name": f"{name} — budget",
            "amount_micros": cents_to_micros(budget.daily_cents),
            "delivery_method": "STANDARD",
        },
        "campaign": {
            "name": name,
            "status": "PAUSED",
            "advertising_channel_type": "SEARCH" if objective == "traffic" else "DISPLAY",
            "start_date": schedule.start_at.strftime("%Y%m%d"),
            "end_date": schedule.end_at.strftime("%Y%m%d"),
            "account_ref": account_ref,
        },
        "ad_group": {
            "name": f"{name} — ad group",
            "status": "PAUSED",
            **targeting,
        },
        "criterion": {
            "proximity": [
                {
                    "latitude_in_micro_degrees": int(round(p.latitude * 1_000_000)),
                    "longitude_in_micro_degrees": int(round(p.longitude * 1_000_000)),
                    "radius": p.radius_mi,
                    "radius_units": "MILES",
                }
                for p in geo.custom_locations
            ]
        },
        "ad": {
            "name": f"{name} — ad",
            "status": "PAUSED",
            "headline": creative.headline,
            "description": creative.description,
            "final_url": creative.landing_url,
            "image_ref": creative.image_ref,
        },
    }


# ── public entry point ────────────────────────────────────────────────────────────────────────────
def build_from_template(template: dict, ad_account: dict) -> CampaignPlan:
    """Resolve a stored template + selected ad account into a platform-ready :class:`CampaignPlan`.

    ``template`` is the ``ad_campaign_templates`` row (geo_spec/targeting_spec/schedule_spec/
    budget_spec/creative_spec jsonb + name/objective). ``ad_account`` is the ``ad_accounts`` row;
    ``ad_account['platform']`` ('meta'|'google') selects the request-payload shape.
    """
    platform = ad_account.get("platform")
    if platform not in _VALID_PLATFORMS:
        raise ValueError(f"ad_account.platform must be one of {_VALID_PLATFORMS} (got {platform!r})")

    name = template["name"]
    objective = template["objective"]
    budget = _resolve_budget(template.get("budget_spec", {}))
    schedule = _resolve_schedule(template.get("schedule_spec", {}))
    validate_window(schedule)
    geo = _resolve_geo(template.get("geo_spec", {}))
    creative = _resolve_creative(template.get("creative_spec", {}))
    targeting = dict(template.get("targeting_spec", {}))
    account_ref = ad_account.get("external_account_id", "")

    builder = _meta_requests if platform == "meta" else _google_requests
    requests = builder(
        name=name,
        objective=objective,
        budget=budget,
        schedule=schedule,
        geo=geo,
        creative=creative,
        targeting=targeting,
        account_ref=account_ref,
    )

    return CampaignPlan(
        platform=platform,
        name=name,
        objective=objective,
        budget=budget,
        schedule=schedule,
        geo=geo,
        creative=creative,
        targeting=targeting,
        requests=requests,
    )
