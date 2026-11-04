"""The Meta Ads client boundary — fixture (deterministic, offline) + live (fail-closed) (ADR 0009).

A config-driven factory (:func:`get_meta_ads_client`) returns the fixture-backed client by default and
the fail-closed live skeleton when ``ads_mode='live'``. The shape mirrors the other integration
adapters here (``booking_intake.client`` / construction live skeletons): a ``Protocol`` defines the
read+write surface; the fixture client returns stable ids + canned metrics; the live client RAISES on
every write so a misconfigured go-live can NEVER fabricate a campaign or a conversion (ADR 0003).

POSTURE (load-bearing):
  * The pure engine already computed every figure (budget cents, schedule, micro-degrees) into
    ``plan.requests`` — this client never recomputes money; it only ships the prebuilt payload.
  * Reads (``get_insights`` / ``list_lead_forms`` / ``get_leads``) are safe; WRITES
    (``create_campaign`` / ``send_conversion`` / ``pause_campaign`` / ``activate_campaign``) are the
    gated surface — fixture simulates them deterministically, live fails closed.
  * ``send_conversion`` receives an ALREADY-HASHED payload (SHA-256 per ``app/ads/pii.py``); this
    client never sees or logs plaintext PII.
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from app.ads.schemas import CampaignPlan
from app.config import Settings, get_settings

# A stable, filesystem/url-safe slug for deterministic fixture ids (lowercase, non-alnum -> single '-').
_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slug(name: str) -> str:
    """Lowercase + collapse non-alphanumerics to ``-`` so fixture ids are stable and readable."""
    return _SLUG_NON_ALNUM.sub("-", name.lower()).strip("-")


@runtime_checkable
class MetaAdsClient(Protocol):
    """The Meta Ads surface the ad agent + action executors need (reads safe; writes gated)."""

    async def create_campaign(self, plan: CampaignPlan) -> dict:
        """Create a PAUSED campaign from a platform-ready plan; returns the created object ids."""
        ...

    async def get_insights(self, campaign_ref: str) -> dict:
        """Read delivery metrics for a campaign (spend cents / impressions / clicks / leads)."""
        ...

    async def list_lead_forms(self) -> list[dict]:
        """List the lead-gen forms available on the connected ad account."""
        ...

    async def get_leads(self, form_ref: str) -> list[dict]:
        """Read the leads captured by one lead-gen form."""
        ...

    async def send_conversion(self, hashed_payload: dict) -> dict:
        """Upload an offline/server conversion (payload PII already SHA-256 hashed); returns receipt."""
        ...

    async def pause_campaign(self, campaign_ref: str) -> dict:
        """Set a campaign's status to PAUSED; returns the new status."""
        ...

    async def activate_campaign(self, campaign_ref: str) -> dict:
        """Set a campaign's status to ACTIVE; returns the new status."""
        ...


class FixtureMetaAdsClient:
    """Deterministic, fully-offline Meta client for demos + tests (``ads_mode != 'live'``).

    Every id is a pure function of its inputs (``meta-camp-<slug>`` etc.) so oracles can assert exact
    values, and every metric is canned — there is NO network access and NO randomness.
    """

    async def create_campaign(self, plan: CampaignPlan) -> dict:
        slug = _slug(plan.name)
        return {
            "campaign_ref": f"meta-camp-{slug}",
            "adset_ref": f"meta-adset-{slug}",
            "adcreative_ref": f"meta-creative-{slug}",
            "ad_ref": f"meta-ad-{slug}",
            "status": "PAUSED",  # PAUSED-on-create (ADR 0007) — nothing goes live without approve->execute.
        }

    async def get_insights(self, campaign_ref: str) -> dict:
        # Canned, deterministic delivery metrics. Money in integer CENTS (our domain unit).
        return {
            "campaign_ref": campaign_ref,
            "spend_cents": 4200,
            "impressions": 18_400,
            "clicks": 412,
            "leads": 23,
            "ctr": 0.0224,
            "cpl_cents": 183,  # 4200c spend / 23 leads ~= 182.6c, fixed for stability.
        }

    async def list_lead_forms(self) -> list[dict]:
        return [
            {"form_ref": "meta-leadform-demo-request", "name": "Demo Request", "leads_count": 23},
            {"form_ref": "meta-leadform-pricing", "name": "Pricing Sheet", "leads_count": 11},
        ]

    async def get_leads(self, form_ref: str) -> list[dict]:
        return [
            {
                "lead_ref": f"meta-lead-{form_ref}-1",
                "form_ref": form_ref,
                "full_name": "Sam Contractor",
                "company": "Summit Heat Pumps",
                "created_at": "2026-06-20T15:04:00+00:00",
            },
            {
                "lead_ref": f"meta-lead-{form_ref}-2",
                "form_ref": form_ref,
                "full_name": "Pat Owner",
                "company": "Summit Mechanical",
                "created_at": "2026-06-21T09:31:00+00:00",
            },
        ]

    async def send_conversion(self, hashed_payload: dict) -> dict:
        # Echo only NON-PII metadata back; the hashed identifiers are accepted but never reflected/logged.
        event_name = hashed_payload.get("event_name", "Lead")
        return {
            "received": 1,
            "event_name": event_name,
            "fbtrace_id": f"meta-capi-{_slug(str(event_name))}",
        }

    async def pause_campaign(self, campaign_ref: str) -> dict:
        return {"campaign_ref": campaign_ref, "status": "PAUSED"}

    async def activate_campaign(self, campaign_ref: str) -> dict:
        return {"campaign_ref": campaign_ref, "status": "ACTIVE"}


class LiveMetaAdsClient:
    """Live Meta Marketing/Conversions API skeleton — fail-closed (``ads_mode='live'``).

    Reads are left as NotImplementedError stubs (map the real Graph API response shapes against a live
    account at go-live, exactly as the construction/ServiceTitan live skeletons do). Every WRITE RAISES
    immediately so a half-configured live mode can never silently fabricate a campaign or a conversion
    (ADR 0003 fail-closed). The real write path runs through the action gate (propose->approve->execute),
    not here — this client must NEVER become a parallel write path.
    """

    def __init__(self, settings: Settings) -> None:
        self._s = settings

    def _require_credentials(self) -> None:
        missing = [
            name
            for name, value in {
                "META_APP_ID": self._s.meta_app_id,
                "META_APP_SECRET": self._s.meta_app_secret,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError("Meta live mode requires: " + ", ".join(missing))

    async def create_campaign(self, plan: CampaignPlan) -> dict:
        raise NotImplementedError(
            "live Meta write not yet wired: POST campaign/adset/adcreative/ad from plan.requests "
            "(all PAUSED) via the action gate, then map the returned ids."
        )

    async def get_insights(self, campaign_ref: str) -> dict:
        raise NotImplementedError(
            "Map Meta Graph /insights for a campaign -> {spend_cents, impressions, clicks, leads} "
            "(verify spend currency/units against the live account)."
        )

    async def list_lead_forms(self) -> list[dict]:
        raise NotImplementedError(
            "Map Meta Graph /leadgen_forms on the connected ad account -> [{form_ref, name, ...}]."
        )

    async def get_leads(self, form_ref: str) -> list[dict]:
        raise NotImplementedError(
            "Map Meta Graph /{form}/leads -> [{lead_ref, field_data, ...}] (verify field_data shape)."
        )

    async def send_conversion(self, hashed_payload: dict) -> dict:
        raise NotImplementedError(
            "live Meta write not yet wired: POST the (already SHA-256 hashed) payload to the "
            "Conversions API /{pixel_id}/events via the action gate; never send plaintext PII."
        )

    async def pause_campaign(self, campaign_ref: str) -> dict:
        raise NotImplementedError(
            "live Meta write not yet wired: POST status=PAUSED on the campaign via the action gate."
        )

    async def activate_campaign(self, campaign_ref: str) -> dict:
        raise NotImplementedError(
            "live Meta write not yet wired: POST status=ACTIVE on the campaign via the action gate."
        )


def get_meta_ads_client(settings: Settings | None = None) -> MetaAdsClient:
    """Return the live Meta client when ``ads_mode='live'``, else the deterministic fixture client."""
    settings = settings or get_settings()
    if settings.ads_mode.lower() == "live":
        return LiveMetaAdsClient(settings)
    return FixtureMetaAdsClient()
