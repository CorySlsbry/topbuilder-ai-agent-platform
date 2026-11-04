"""Trade-show geofence campaign-template seeds (ADR 0009).

Builds the deterministic ``ad_campaign_templates`` rows for Top Builder AI's 2026 trade-show run from
the human-authored source-of-truth markdown under ``marketing/trade-shows/2026-06-22/`` — geofence pins
+ radius from ``geofence-configs.md``, creative copy (Variant A) from ``ad-copy.md``, the per-show landing
page, and the capped budget. EVERY value here is transcribed from those files (nothing is invented), so
re-deriving the seed always reproduces the same templates.

Spec shapes match the jsonb the engine resolves (``app/ads/engine.py`` ``_resolve_*``):
  * geo_spec      — ``{custom_locations: [{lat, long, radius_mi}], location_type}``  (Meta "recently in")
  * targeting_spec— ``{interests: [...], age_min, age_max}``  (the reusable detailed-targeting layer)
  * schedule_spec — ``{start_at, end_at, tz}``  (ISO-8601 strings, the show days)
  * budget_spec   — ``{daily_cents, lifetime_cap_cents}``  (integer CENTS — our canonical money unit)
  * creative_spec — ``{headline, primary_text, description, landing_url, image_ref}``  (ad-copy Variant A)

``seed_templates`` is idempotent: it UPSERTs on ``slug`` via ``repositories.ads.create_template`` (the
``ON CONFLICT (slug)`` path), so a re-run refreshes the rows in place rather than duplicating them. It is
operator-scoped — the caller opens an ``operator_session()`` (see ``scripts/seed_ads_templates.py``).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import ads as ads_repo

# The reusable detailed-targeting layer applied to every show (geofence-configs.md "Reusable …" block +
# the Meta detailed-targeting list in meta-google-runbook-nashville.md step 10). Age 28–65+ per the runbook.
_REUSABLE_INTERESTS: tuple[str, ...] = (
    "ServiceTitan",
    "QuickBooks",
    "Housecall Pro",
    "FieldEdge",
    "Jobber",
    "contractor business",
    "HVAC",
    "Plumbing",
    "Roofing",
    "Small business owners",
    "Construction",
)
_AGE_MIN = 28
_AGE_MAX = 65


def _targeting_spec() -> dict[str, Any]:
    """The shared detailed-targeting layer (interests + age band) every show reuses."""
    return {"interests": list(_REUSABLE_INTERESTS), "age_min": _AGE_MIN, "age_max": _AGE_MAX}


def _geo_spec(custom_locations: list[dict[str, float]]) -> dict[str, Any]:
    """A geofence: custom radius pins + Meta's 'recently in this location' intent (geofence-configs.md)."""
    return {"custom_locations": custom_locations, "location_type": "recent"}


# ── per-show template specs (verbatim from the trade-show markdown) ───────────────────────────────────
# Each entry is the FULL ad_campaign_templates row payload for repositories.ads.create_template. Values:
#   geo pins + radius   → geofence-configs.md (the section noted)
#   schedule (UTC ISO)  → geofence-configs.md "Schedule" line / the show days
#   budget (cents)      → geofence-configs.md "Budget" line, converted to integer cents
#   creative Variant A  → ad-copy.md (the section noted)
#   landing_url         → geofence-configs.md "Destination"
_TEMPLATE_SPECS: tuple[dict[str, Any], ...] = (
    # 1) Build Expo Nashville — geofence-configs.md §1 + ad-copy.md §1 (Variant A). $10/day × 2d, cap $20.
    {
        "slug": "build-expo-nashville-2026",
        "name": "Build Expo Nashville 2026 — Geofence",
        "objective": "traffic",
        "geo_spec": _geo_spec(
            [
                # Music City Center pin — 1.0 mi (covers the convention core + downtown hotels).
                {"lat": 36.1565, "long": -86.7766, "radius_mi": 1.0},
                # Host-hotel pins (geofence-configs.md §1 "Add host-hotel pins").
                {"lat": 36.1558, "long": -86.7758, "radius_mi": 0.5},  # Omni Nashville Hotel
                {"lat": 36.1592, "long": -86.7758, "radius_mi": 0.5},  # Hilton Nashville Downtown
                {"lat": 36.1565, "long": -86.7820, "radius_mi": 0.5},  # JW Marriott Nashville
            ]
        ),
        "targeting_spec": _targeting_spec(),
        # Jul 1 8a – Jul 2 6p CT (CDT = UTC-5). Run window 2026-06-30..2026-07-02 per the task anchor.
        "schedule_spec": {
            "start_at": "2026-06-30T00:00:00",
            "end_at": "2026-07-02T23:00:00",
            "tz": "America/Chicago",
        },
        "budget_spec": {"daily_cents": 1000, "lifetime_cap_cents": 2000},  # $10/day, $20 cap
        "creative_spec": {
            "headline": "The AI back office, in 5 minutes",
            "primary_text": (
                "At Build Expo Nashville this week? I'm not on the floor — but here's the 5-minute "
                "version of the AI back office every ServiceTitan + QuickBooks shop is asking about. "
                "Eight self-learning agents that run the Money, Materials, People, and Paperwork your "
                "software can't. Book a 15-minute virtual walkthrough — see your own back office, not "
                "a generic deck."
            ),
            "description": "For $1M–$50M contractors on ServiceTitan + QuickBooks",
            "landing_url": "https://topbuilderai.com/shows/build-expo-nashville-2026",
            "image_ref": None,
        },
    },
    # 2) Build Expo Houston — geofence-configs.md §2 + ad-copy.md §2 (Variant A). $12/day × 2d, cap $24.
    {
        "slug": "build-expo-houston-2026",
        "name": "Build Expo Houston 2026 — Geofence",
        "objective": "traffic",
        "geo_spec": _geo_spec(
            [
                # NRG Center pin — 1.0 mi (covers all halls + lots).
                {"lat": 29.6847, "long": -95.4107, "radius_mi": 1.0},
                # Nearby-hotel pins (geofence-configs.md §2 "Add nearby-hotel pins").
                {"lat": 29.7095, "long": -95.4000, "radius_mi": 1.0},  # Houston Marriott Med Center/Museum
                {"lat": 29.7090, "long": -95.3980, "radius_mi": 1.0},  # Hilton Houston Plaza/Medical Center
            ]
        ),
        "targeting_spec": _targeting_spec(),
        # Aug 11 9a – Aug 12 4p CT.
        "schedule_spec": {
            "start_at": "2026-08-11T00:00:00",
            "end_at": "2026-08-12T21:00:00",
            "tz": "America/Chicago",
        },
        "budget_spec": {"daily_cents": 1200, "lifetime_cap_cents": 2400},  # $12/day, $24 cap
        "creative_spec": {
            "headline": "The AI back office, in 5 minutes",
            "primary_text": (
                "Headed to Build Expo Houston at NRG Center? 250+ booths, and the thing every "
                "ServiceTitan + QuickBooks shop is actually asking about isn't one of them. Eight "
                "self-learning AI agents that run the Money, Materials, People, and Paperwork your "
                "software can't — and get smarter every week on your shop. Book a 15-minute virtual "
                "walkthrough."
            ),
            "description": "For $1M–$50M contractors on ServiceTitan + QuickBooks",
            "landing_url": "https://topbuilderai.com/shows/build-expo-houston-2026",
            "image_ref": None,
        },
    },
    # 3) Western Roofing Expo — geofence-configs.md §3 + ad-copy.md §3 (Variant A). $10/day × 3d, cap $30.
    {
        "slug": "western-roofing-expo-2026",
        "name": "Western Roofing Expo 2026 — Geofence",
        "objective": "traffic",
        "geo_spec": _geo_spec(
            [
                # Paris Las Vegas pin — 1.0 mi (central Strip + adjacent hotels).
                {"lat": 36.1126, "long": -115.1709, "radius_mi": 1.0},
                # Adjacent-hotel pins (geofence-configs.md §3 "Add host/adjacent-hotel pins").
                {"lat": 36.1116, "long": -115.1726, "radius_mi": 0.5},  # Horseshoe Las Vegas
                {"lat": 36.1095, "long": -115.1710, "radius_mi": 0.5},  # Bally's/Planet Hollywood cluster
            ]
        ),
        "targeting_spec": _targeting_spec(),
        # Sept 27 8a – Sept 29 5p PT.
        "schedule_spec": {
            "start_at": "2026-09-27T00:00:00",
            "end_at": "2026-09-29T22:00:00",
            "tz": "America/Los_Angeles",
        },
        "budget_spec": {"daily_cents": 1000, "lifetime_cap_cents": 3000},  # $10/day × 3d, $30 cap
        "creative_spec": {
            "headline": "The AI back office for roofers",
            "primary_text": (
                "At the Western Roofing Expo? On a roofing job, a few mispriced squares is the whole "
                "profit. Here's what every roofer on ServiceTitan + QuickBooks is asking about: eight "
                "self-learning AI agents that re-price shingles and membrane the day supplier costs "
                "change, flag the AR slipping, and catch expiring COIs. Book a 15-minute virtual "
                "walkthrough."
            ),
            "description": "For $1M–$50M roofing shops on ServiceTitan + QBO",
            "landing_url": "https://topbuilderai.com/shows/western-roofing-expo-2026",
            "image_ref": None,
        },
    },
    # 4) ServiceTitan Pantheon — geofence-configs.md §4 + ad-copy.md §4 (Variant A). $12/day × 3d, cap $36.
    {
        "slug": "servicetitan-pantheon-2026",
        "name": "ServiceTitan Pantheon 2026 — Geofence",
        "objective": "traffic",
        "geo_spec": _geo_spec(
            [
                # Swan & Dolphin pin — 1.0 mi (ServiceTitan takes the whole Swan/Dolphin campus).
                {"lat": 28.3625, "long": -81.5586, "radius_mi": 1.0},
                # Adjacent Epcot-resort pins (geofence-configs.md §4 "Add adjacent Epcot-resort pins").
                {"lat": 28.3618, "long": -81.5598, "radius_mi": 0.5},  # Walt Disney World Dolphin
                {"lat": 28.3690, "long": -81.5570, "radius_mi": 0.5},  # Disney's BoardWalk Inn
                {"lat": 28.3705, "long": -81.5560, "radius_mi": 0.5},  # Disney's Yacht & Beach Club
            ]
        ),
        "targeting_spec": _targeting_spec(),
        # Oct 5 8a – Oct 7 6p ET.
        "schedule_spec": {
            "start_at": "2026-10-05T00:00:00",
            "end_at": "2026-10-07T22:00:00",
            "tz": "America/New_York",
        },
        "budget_spec": {"daily_cents": 1200, "lifetime_cap_cents": 3600},  # $12/day × 3d, $36 cap
        "creative_spec": {
            "headline": "The back office ST has no agents for",
            "primary_text": (
                "At Pantheon? You'll see everything ServiceTitan does for your front office. Here's "
                "what it has no agents for: the Money, Materials, People, and Paperwork in your back "
                "office. Eight self-learning AI agents that sit on top of the ServiceTitan + "
                "QuickBooks data you already trust — and get smarter every week. Book a 15-minute "
                "virtual walkthrough."
            ),
            "description": "Sits on top of your ServiceTitan + QuickBooks",
            "landing_url": "https://topbuilderai.com/shows/servicetitan-pantheon-2026",
            "image_ref": None,
        },
    },
)


def template_specs() -> list[dict[str, Any]]:
    """The deterministic list of trade-show template payloads (pure — no DB, unit-testable)."""
    return [dict(spec) for spec in _TEMPLATE_SPECS]


async def seed_templates(session: AsyncSession) -> list[dict]:
    """Idempotently UPSERT every trade-show geofence template; return the persisted rows.

    Operator-scoped — open the ``session`` via ``db.operator_session()`` so the operator-only RLS policy
    (migration 0023) grants access. Each spec is written through ``repositories.ads.create_template``,
    which UPSERTs on ``slug`` (``ON CONFLICT (slug) DO UPDATE``), so a re-run refreshes rows in place.
    """
    rows: list[dict] = []
    for spec in template_specs():
        row = await ads_repo.create_template(
            session,
            slug=spec["slug"],
            name=spec["name"],
            objective=spec["objective"],
            template_type="trade_show_geofence",
            geo_spec=spec["geo_spec"],
            targeting_spec=spec["targeting_spec"],
            schedule_spec=spec["schedule_spec"],
            budget_spec=spec["budget_spec"],
            creative_spec=spec["creative_spec"],
        )
        rows.append(row)
    return rows
