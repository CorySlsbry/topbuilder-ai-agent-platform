"""The Google Ads adapter boundary (Ads-CRM, ADR 0009).

Callers depend only on the :class:`GoogleAdsClient` protocol. A config-driven factory returns either a
deterministic FIXTURE client (``ads_mode!='live'`` — fully offline, hand-checkable ids + canned GAQL
metrics, so the whole Ads-CRM is testable with NO live API) or a LIVE skeleton that FAILS CLOSED:
every method raises rather than ever fabricating a success in live mode (ADR 0007 — a write must be
real or refuse), and the factory itself refuses to hand back a live client when the Google-approved
``google_ads_developer_token`` is unset (no live Google Ads call is possible without it).

The deterministic ids/metrics here come from PURE code, never the LLM (ADR 0003). Money on the way IN
is already in the platform's own units inside ``plan.requests`` (``amount_micros`` etc.), computed by
``app.ads.engine``; this adapter does not recompute any figure. Every create payload is PAUSED-on-create
upstream — this boundary just POSTs whatever the engine assembled.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.ads.schemas import CampaignPlan
from app.config import Settings, get_settings


@runtime_checkable
class GoogleAdsClient(Protocol):
    """The Google Ads write/read surface the Ads-CRM action executors depend on."""

    async def create_campaign(self, plan: CampaignPlan) -> dict:
        """Create budget→campaign→ad_group→criterion→ad (all PAUSED) and return the resource ids."""
        ...

    async def get_metrics(self, gaql: str) -> dict:
        """Run a GAQL query and return aggregate campaign metrics (impressions/clicks/cost/conv.)."""
        ...

    async def import_offline_conversion(self, hashed: dict) -> dict:
        """Upload an offline/enhanced conversion built from SHA-256-hashed user identifiers."""
        ...

    async def pause_campaign(self, campaign_resource_name: str) -> dict:
        """Set a campaign's status to PAUSED (spend-reducing — safe)."""
        ...

    async def activate_campaign(self, campaign_resource_name: str) -> dict:
        """Set a campaign's status to ENABLED (spend-committing — gated upstream by HITL)."""
        ...


def _slug(value: str) -> str:
    """Stable, id-safe token from a campaign name (lowercase, non-alnum→single dash, trimmed)."""
    out: list[str] = []
    prev_dash = False
    for ch in value.strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    return "".join(out).strip("-") or "campaign"


class FixtureGoogleAdsClient:
    """Deterministic, fully-offline Google Ads client.

    Ids are derived purely from the plan name (``google-camp-<slug>`` and siblings) so tests can assert
    them by hand; ``get_metrics`` returns a canned, stable metrics block. No network, no secrets.
    """

    async def create_campaign(self, plan: CampaignPlan) -> dict:
        slug = _slug(plan.name)
        return {
            "budget_resource_name": f"google-budget-{slug}",
            "campaign_resource_name": f"google-camp-{slug}",
            "ad_group_resource_name": f"google-adgroup-{slug}",
            "criterion_resource_name": f"google-criterion-{slug}",
            "ad_resource_name": f"google-ad-{slug}",
            "status": "PAUSED",
            "external_ref": f"google-camp-{slug}",
        }

    async def get_metrics(self, gaql: str) -> dict:
        # Canned, deterministic aggregate (cost in micros, Google's money unit) — independent of the query.
        return {
            "query": gaql,
            "impressions": 12000,
            "clicks": 480,
            "cost_micros": 360_000_000,  # = $360.00 (360_000_000 / 1_000_000)
            "conversions": 24,
            "conversions_value_micros": 4_800_000_000,  # = $4,800.00
        }

    async def import_offline_conversion(self, hashed: dict) -> dict:
        return {
            "received": True,
            "conversion_action": hashed.get("conversion_action"),
            "external_ref": f"google-conv-{hashed.get('order_id', 'fixture')}",
            "status": "RECEIVED",
        }

    async def pause_campaign(self, campaign_resource_name: str) -> dict:
        return {"campaign_resource_name": campaign_resource_name, "status": "PAUSED"}

    async def activate_campaign(self, campaign_resource_name: str) -> dict:
        return {"campaign_resource_name": campaign_resource_name, "status": "ENABLED"}


class LiveGoogleAdsClient:
    """Live Google Ads client skeleton — FAILS CLOSED on every call (ADR 0007).

    The OAuth refresh + REST/gRPC mapping must be wired and verified against a real Google Ads account
    (and a Google-APPROVED developer token + optional MCC ``login-customer-id`` header) before this can
    perform real writes. Until then every method raises ``NotImplementedError`` so live mode can NEVER
    fabricate a success — exactly mirroring the ServiceTitan live skeleton.
    """

    def __init__(self, settings: Settings) -> None:
        self._s = settings

    def _require_developer_token(self) -> None:
        if not self._s.google_ads_developer_token:
            raise RuntimeError(
                "Google Ads live mode requires GOOGLE_ADS_DEVELOPER_TOKEN (a Google-approved token)."
            )

    async def create_campaign(self, plan: CampaignPlan) -> dict:
        self._require_developer_token()
        # POST budget→campaign→ad_group→criterion→ad via google_ads_api_base, all PAUSED (plan.requests).
        raise NotImplementedError(
            "Live Google Ads create_campaign not yet wired — verify the GoogleAdsService mutate shapes "
            "against a real account before enabling (fail closed; never fabricate a campaign id)."
        )

    async def get_metrics(self, gaql: str) -> dict:
        self._require_developer_token()
        # POST searchStream to customers/{id}/googleAds:searchStream with the GAQL body.
        raise NotImplementedError("Live Google Ads get_metrics (GAQL searchStream) not yet wired.")

    async def import_offline_conversion(self, hashed: dict) -> dict:
        self._require_developer_token()
        # uploadClickConversions / uploadConversionAdjustments with hashed identifiers.
        raise NotImplementedError("Live Google Ads import_offline_conversion not yet wired.")

    async def pause_campaign(self, campaign_resource_name: str) -> dict:
        self._require_developer_token()
        raise NotImplementedError("Live Google Ads pause_campaign not yet wired.")

    async def activate_campaign(self, campaign_resource_name: str) -> dict:
        self._require_developer_token()
        raise NotImplementedError("Live Google Ads activate_campaign not yet wired.")


def get_google_ads_client(*, settings: Settings | None = None) -> GoogleAdsClient:
    """Return the live skeleton when ``ads_mode='live'`` (and the developer token is set), else fixture.

    Live mode without a Google-approved developer token cannot make any Google Ads call, so the factory
    raises rather than returning a half-configured live client that would fail deep in a write.
    """
    settings = settings or get_settings()
    if settings.ads_mode.lower() == "live":
        if not settings.google_ads_developer_token:
            raise RuntimeError(
                "ads_mode='live' requires GOOGLE_ADS_DEVELOPER_TOKEN (a Google-approved token) — "
                "refusing to return a live Google Ads client without it (fail closed)."
            )
        return LiveGoogleAdsClient(settings)
    return FixtureGoogleAdsClient()
