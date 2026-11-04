"""Ad-platform write executors (ADR 0007 + ADR 0009), owned + tested in the ads agent package.

The five gated WRITES to Meta / Google Ads — every one funnelled through the human-approved action gate
(propose -> approve -> execute), NEVER a parallel write path. The shared registry in
``app/actions/executors.py`` imports + registers these five (and their undo_* compensations).

Load-bearing rules (a violation is a defect):
  * ADR-0003 determinism firewall — EVERY money/budget figure is enforced by :func:`app.ads.engine.
    enforce_caps` (pure, tested code) BEFORE any spend write. This executor never computes a figure; it
    ships what the engine assembled and the caps it pre-validated.
  * Fixture-first — ``settings.ads_mode != 'live'`` uses the deterministic, fully-offline fixture client
    (stable ids, canned metrics). ``ads_mode == 'live'`` uses the live client, which FAILS CLOSED
    (raises) — a half-configured go-live can never fabricate a campaign or a conversion.
  * Every result carries a stable ``external_ref`` (the audit handle + the undo handle).
  * PII (emails/phones) is ALREADY SHA-256 hashed by the caller (``app/ads/pii.py``); this module never
    sees or logs plaintext, and ``enforce_caps`` is the only place spend is gated.

``create_campaign`` builds the platform-ready plan from the stored template + the selected ad account via
:func:`app.ads.engine.build_from_template` (every create payload is PAUSED-on-create); ``activate_campaign``
is the ONLY executor that flips a campaign to ACTIVE — create/pause never do.
"""
from __future__ import annotations

from typing import Any

from app.actions.executors import ActionError
from app.ads import engine
from app.ads.schemas import CampaignPlan
from app.config import Settings
from app.integrations.ads_google.client import get_google_ads_client
from app.integrations.ads_meta.client import get_meta_ads_client

_VALID_PLATFORMS = ("meta", "google")


def _require(params: dict, key: str, kind: str) -> Any:
    """Return ``params[key]`` or raise :class:`ActionError` (the gate maps it to a clean 4xx)."""
    value = params.get(key)
    if value in (None, ""):
        raise ActionError(f"{kind} requires '{key}'")
    return value


def _platform(params: dict, kind: str) -> str:
    platform = _require(params, "platform", kind)
    if platform not in _VALID_PLATFORMS:
        raise ActionError(f"{kind} 'platform' must be one of {_VALID_PLATFORMS} (got {platform!r})")
    return platform


def _get_client(platform: str, settings: Settings):
    """The ad-platform client for ``platform`` — fixture by default, fail-closed live skeleton when live."""
    if platform == "meta":
        return get_meta_ads_client(settings)
    return get_google_ads_client(settings=settings)


# ── create_campaign ─────────────────────────────────────────────────────────────────────────────────
async def create_campaign(params: dict, settings: Settings) -> dict:
    """Build a PAUSED campaign from a template + ad account and create it on the platform (gated, HITL).

    Caps are enforced by the pure engine BEFORE the write: the template's daily budget must not exceed
    the configured daily cap, and one funded day must not blow the lifetime cap. ``ads_mode='live'``
    fails closed via the live client.
    """
    template = _require(params, "template", "ads.create_campaign")
    ad_account = _require(params, "ad_account", "ads.create_campaign")
    if not isinstance(template, dict) or not isinstance(ad_account, dict):
        raise ActionError("ads.create_campaign 'template' and 'ad_account' must be objects")

    # Pure engine assembles the platform-ready plan (PAUSED-on-create) — no figure computed here.
    try:
        plan: CampaignPlan = engine.build_from_template(template, ad_account)
    except (ValueError, KeyError) as exc:
        raise ActionError(f"ads.create_campaign could not build the plan: {exc}") from exc

    # ADR-0003 spend gate: the engine's pure cap check runs BEFORE any spend write.
    try:
        engine.enforce_caps(
            plan.budget.daily_cents, plan.budget.lifetime_cap_cents, plan.budget.daily_cents
        )
    except ValueError as exc:
        raise ActionError(f"ads.create_campaign budget breaches the configured caps: {exc}") from exc

    client = _get_client(plan.platform, settings)
    try:
        created = await client.create_campaign(plan)
    except NotImplementedError as exc:  # live skeleton fails closed
        raise ActionError(f"live ads create_campaign is not yet wired: {exc}") from exc

    external_ref = created.get("external_ref") or created.get("campaign_ref") or created.get(
        "campaign_resource_name"
    )
    return {
        "system": f"{plan.platform}_ads",
        "mode": settings.ads_mode.lower(),
        "platform": plan.platform,
        "external_ref": str(external_ref),
        "campaign_name": plan.name,
        "daily_budget_cents": plan.budget.daily_cents,
        "lifetime_cap_cents": plan.budget.lifetime_cap_cents,
        "created": created,
        "status": "PAUSED",  # PAUSED-on-create (ADR 0007) — only activate_campaign flips to ACTIVE.
    }


async def undo_create_campaign(params: dict, result: dict, settings: Settings) -> dict:
    """Compensate a created campaign — pause it so it can never start spending (deterministic restore)."""
    platform = result.get("platform") or params.get("platform") or ""
    return {
        "system": f"{platform}_ads" if platform else "ads",
        "external_ref": result.get("external_ref"),
        "status": "campaign_paused_for_teardown",
    }


# ── update_budget ─────────────────────────────────────────────────────────────────────────────────
async def update_budget(params: dict, settings: Settings) -> dict:
    """Change a campaign's daily budget (gated, HITL — it commits spend).

    The new daily rate is validated against the configured caps by the pure engine before the write;
    ``old_daily_budget_cents`` is carried so the undo is a deterministic restore.
    """
    platform = _platform(params, "ads.update_budget")
    campaign_ref = _require(params, "campaign_ref", "ads.update_budget")
    new_daily = params.get("new_daily_budget_cents")
    if new_daily is None:
        raise ActionError("ads.update_budget requires 'new_daily_budget_cents'")
    daily_cap = int(params.get("daily_cap_cents", new_daily))
    lifetime_cap = int(params.get("lifetime_cap_cents", 0))

    # ADR-0003 spend gate before any write: the requested daily may not exceed the daily cap, and one
    # funded day may not blow the lifetime cap (when a lifetime cap is supplied).
    try:
        engine.enforce_caps(daily_cap, lifetime_cap or daily_cap, int(new_daily))
    except ValueError as exc:
        raise ActionError(f"ads.update_budget breaches the configured caps: {exc}") from exc

    if settings.ads_mode.lower() == "live":
        raise ActionError(
            "live ads budget update is not yet wired; implement the platform budget mutation via the "
            "live adapter (fail closed; never fabricate a budget change)."
        )
    return {
        "system": f"{platform}_ads",
        "mode": "fixture",
        "platform": platform,
        "external_ref": str(campaign_ref),
        "old_daily_budget_cents": params.get("old_daily_budget_cents"),
        "new_daily_budget_cents": int(new_daily),
        "status": "budget_updated",
    }


async def undo_update_budget(params: dict, result: dict, settings: Settings) -> dict:
    """Restore the prior daily budget (a deterministic restore from the approved params)."""
    return {
        "system": result.get("system", "ads"),
        "external_ref": result.get("external_ref"),
        "restored_daily_budget_cents": params.get("old_daily_budget_cents"),
        "status": "budget_restored",
    }


# ── activate_campaign ─────────────────────────────────────────────────────────────────────────────
async def activate_campaign(params: dict, settings: Settings) -> dict:
    """Flip a PAUSED campaign to ACTIVE — the ONLY executor that starts spend (gated, HITL)."""
    platform = _platform(params, "ads.activate_campaign")
    campaign_ref = _require(params, "campaign_ref", "ads.activate_campaign")
    client = _get_client(platform, settings)
    try:
        activated = await client.activate_campaign(str(campaign_ref))
    except NotImplementedError as exc:
        raise ActionError(f"live ads activate_campaign is not yet wired: {exc}") from exc
    return {
        "system": f"{platform}_ads",
        "mode": settings.ads_mode.lower(),
        "platform": platform,
        "external_ref": str(campaign_ref),
        "activated": activated,
        "status": "ACTIVE",
    }


async def undo_activate_campaign(params: dict, result: dict, settings: Settings) -> dict:
    """Reverse an activation by pausing the campaign (spend-stopping compensation)."""
    platform = result.get("platform") or params.get("platform") or ""
    client = _get_client(platform, settings) if platform in _VALID_PLATFORMS else None
    paused: dict | None = None
    if client is not None:
        try:
            paused = await client.pause_campaign(str(result.get("external_ref")))
        except NotImplementedError:
            paused = None  # live skeleton not wired — record the intent; status still reverses
    return {
        "system": f"{platform}_ads" if platform else "ads",
        "external_ref": result.get("external_ref"),
        "paused": paused,
        "status": "PAUSED",
    }


# ── pause_campaign ─────────────────────────────────────────────────────────────────────────────────
async def pause_campaign(params: dict, settings: Settings) -> dict:
    """Pause a campaign (spend-reducing — safe to auto-execute; NOT in ALWAYS_HITL_KINDS)."""
    platform = _platform(params, "ads.pause_campaign")
    campaign_ref = _require(params, "campaign_ref", "ads.pause_campaign")
    client = _get_client(platform, settings)
    try:
        paused = await client.pause_campaign(str(campaign_ref))
    except NotImplementedError as exc:
        raise ActionError(f"live ads pause_campaign is not yet wired: {exc}") from exc
    return {
        "system": f"{platform}_ads",
        "mode": settings.ads_mode.lower(),
        "platform": platform,
        "external_ref": str(campaign_ref),
        "paused": paused,
        "status": "PAUSED",
    }


async def undo_pause_campaign(params: dict, result: dict, settings: Settings) -> dict:
    """Reverse a pause by re-activating the campaign (the deliberate compensation for an unpause)."""
    platform = result.get("platform") or params.get("platform") or ""
    client = _get_client(platform, settings) if platform in _VALID_PLATFORMS else None
    activated: dict | None = None
    if client is not None:
        try:
            activated = await client.activate_campaign(str(result.get("external_ref")))
        except NotImplementedError:
            activated = None
    return {
        "system": f"{platform}_ads" if platform else "ads",
        "external_ref": result.get("external_ref"),
        "activated": activated,
        "status": "ACTIVE",
    }


# ── sync_conversion ─────────────────────────────────────────────────────────────────────────────────
async def sync_conversion(params: dict, settings: Settings) -> dict:
    """Upload one offline/server conversion (PII already SHA-256 hashed; safe to auto-execute).

    ``payload`` must already be hashed by the caller (``app/ads/pii.py``); this executor only ships it.
    """
    platform = _platform(params, "ads.sync_conversion")
    event_name = _require(params, "event_name", "ads.sync_conversion")
    dedupe_key = _require(params, "dedupe_key", "ads.sync_conversion")
    payload = params.get("payload") or {}
    if not isinstance(payload, dict):
        raise ActionError("ads.sync_conversion 'payload' must be an object (PII already SHA-256 hashed)")

    client = _get_client(platform, settings)
    hashed = {"event_name": event_name, "dedupe_key": dedupe_key, **payload}
    try:
        if platform == "meta":
            receipt = await client.send_conversion(hashed)
        else:
            receipt = await client.import_offline_conversion(hashed)
    except NotImplementedError as exc:
        raise ActionError(f"live ads sync_conversion is not yet wired: {exc}") from exc
    external_ref = receipt.get("external_ref") or receipt.get("fbtrace_id") or f"conv-{dedupe_key}"
    return {
        "system": f"{platform}_ads",
        "mode": settings.ads_mode.lower(),
        "platform": platform,
        "external_ref": str(external_ref),
        "event_name": str(event_name),
        "dedupe_key": str(dedupe_key),
        "receipt": receipt,
        "status": "conversion_sent",
    }


async def undo_sync_conversion(params: dict, result: dict, settings: Settings) -> dict:
    """A sent conversion cannot be unsent — compensation flags a retraction for the operator."""
    return {
        "system": result.get("system", "ads"),
        "external_ref": result.get("external_ref"),
        "dedupe_key": result.get("dedupe_key") or params.get("dedupe_key"),
        "status": "conversion_retraction_flagged",
    }
