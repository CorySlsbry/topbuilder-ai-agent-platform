"""Ads-CRM orchestration (ADR 0009): plan a campaign into the action gate + the nightly metrics/conversion sync.

Two responsibilities, both operator-scoped:

  * :func:`plan_and_propose` — the engine assembles a platform-ready :class:`CampaignPlan` from a stored
    template + the selected ad account, then we PROPOSE an ``ads.create_campaign`` action through the
    shared human-approved gate (ADR 0007). NOTHING is written to a platform here — proposing is inert;
    a human still approves + executes. The full ``template`` + ``ad_account`` ride in ``params`` so the
    executor rebuilds the SAME plan deterministically at execute time.

  * :func:`sync` — the nightly job: pull each campaign's delivery metrics (fixture client, fully offline)
    into ``ad_metrics`` + roll the running spend onto the campaign row, then FIRE the due
    ``conversion_syncs`` (already-hashed payloads) through the ad-platform client. Idempotent at the DB
    layer (``ON CONFLICT`` on metrics; the conversion ``status`` guard prevents a double send).

Money is integer CENTS in our domain; the engine already converted to the platform's units inside
``plan.requests``. The LLM never computes a figure in here (ADR 0003).
"""
from __future__ import annotations

import uuid
from datetime import date

from app.actions import service as action_service
from app.actions.schemas import ProposeActionIn
from app.ads import engine
from app.config import Settings, get_settings
from app.db import operator_session
from app.integrations.ads_google.client import get_google_ads_client
from app.integrations.ads_meta.client import get_meta_ads_client
from app.repositories import ads as ads_repo
from app.security import Principal


async def plan_and_propose(principal: Principal, *, account: dict, template: dict) -> dict:
    """Build the plan + propose an ``ads.create_campaign`` action; return the proposed action.

    ``account`` is an ``ad_accounts`` row, ``template`` an ``ad_campaign_templates`` row. The engine
    validates the spec + window and assembles the PAUSED-on-create plan; we attach the full template +
    account to ``params`` so the executor recomputes the identical plan, and key the proposal by the
    template slug so a retried propose can't create two campaigns for the same template+account.
    """
    plan = engine.build_from_template(template, account)
    slug = str(template.get("slug") or template.get("id") or plan.name)
    external_account_id = str(account.get("external_account_id") or account.get("id") or "")
    params = {
        "platform": plan.platform,
        "template": template,
        "ad_account": account,
        # surfaced for the approval UI + the audit (the executor still recomputes from template/account).
        "campaign_name": plan.name,
        "daily_budget_cents": plan.budget.daily_cents,
        "lifetime_cap_cents": plan.budget.lifetime_cap_cents,
        # natural key so a retried propose dedupes to the same proposal.
        "id": f"{plan.platform}:{external_account_id}:{slug}",
    }
    payload = ProposeActionIn(
        agent="ads",
        kind="ads.create_campaign",
        params=params,
        idempotency_key=f"ads.create_campaign:{plan.platform}:{external_account_id}:{slug}",
    )
    action = await action_service.propose_action(principal, payload)
    return {
        "action_id": str(action.id),
        "status": action.status,
        "platform": plan.platform,
        "campaign_name": plan.name,
        "daily_budget_cents": plan.budget.daily_cents,
        "lifetime_cap_cents": plan.budget.lifetime_cap_cents,
    }


def _metrics_for(platform: str, insights: dict) -> dict:
    """Normalize a platform's metrics block into our ``ad_metrics`` columns (integer cents).

    Meta's fixture returns ``spend_cents`` directly; Google's returns ``cost_micros`` (1 cent = 10_000
    micros) + ``conversions`` for leads. Pure, hand-checkable — no figure is invented.
    """
    if platform == "meta":
        return {
            "impressions": int(insights.get("impressions", 0)),
            "clicks": int(insights.get("clicks", 0)),
            "landing_page_views": int(insights.get("landing_page_views", 0)),
            "leads": int(insights.get("leads", 0)),
            "spend_cents": int(insights.get("spend_cents", 0)),
        }
    # google: cost is micros; 1 cent = 10_000 micros (the engine's MICROS_PER_CENT, exact integer div).
    cost_micros = int(insights.get("cost_micros", 0))
    return {
        "impressions": int(insights.get("impressions", 0)),
        "clicks": int(insights.get("clicks", 0)),
        "landing_page_views": int(insights.get("landing_page_views", 0)),
        "leads": int(insights.get("conversions", 0)),
        "spend_cents": cost_micros // engine.MICROS_PER_CENT,
    }


async def _pull_campaign_metrics(platform: str, ref: str, settings: Settings) -> dict:
    """Read one campaign's delivery metrics from the platform client (fixture = offline + deterministic)."""
    if platform == "meta":
        client = get_meta_ads_client(settings)
        insights = await client.get_insights(ref)
    else:
        client = get_google_ads_client(settings=settings)
        insights = await client.get_metrics(f"SELECT metrics FROM campaign WHERE campaign='{ref}'")
    return _metrics_for(platform, insights)


async def sync(settings: Settings | None = None, *, day: date | None = None) -> dict:
    """Pull metrics for every live campaign + fire the due conversion sends. Operator-scoped, idempotent.

    Returns a small summary ``{campaigns_synced, conversions_sent, conversions_failed}``. Reads are the
    fixture client by default (fully offline); ``ads_mode='live'`` would route through the live skeleton
    which fails closed. The conversion send reuses the ad-platform client write path.
    """
    settings = settings or get_settings()
    day = day or date.today()
    campaigns_synced = 0
    conversions_sent = 0
    conversions_failed = 0

    async with operator_session() as session:
        # 1) Metrics: roll each non-draft campaign's delivery into ad_metrics + the running spend.
        campaigns = await ads_repo.list_campaigns(session, limit=500)
        for c in campaigns:
            if c["status"] in ("draft", "ended"):
                continue
            ref = c.get("external_campaign_id") or str(c["id"])
            metrics = await _pull_campaign_metrics(c["platform"], ref, settings)
            await ads_repo.upsert_metrics(
                session,
                campaign_id=c["id"],
                day=day,
                impressions=metrics["impressions"],
                clicks=metrics["clicks"],
                landing_page_views=metrics["landing_page_views"],
                leads=metrics["leads"],
                spend_cents=metrics["spend_cents"],
                raw={"source": f"{c['platform']}_sync", "day": day.isoformat()},
            )
            await ads_repo.update_campaign_spend(
                session, campaign_id=c["id"], spend_cents=metrics["spend_cents"]
            )
            campaigns_synced += 1

        # 2) Conversions: fire the pending queue (PII already hashed by the caller) through the client.
        pending = await ads_repo.list_pending_conversion_syncs(session)
        for conv in pending:
            platform = conv["platform"]
            payload = conv.get("payload") or {}
            hashed = {"event_name": conv["event_name"], "dedupe_key": conv["dedupe_key"], **payload}
            try:
                if platform == "meta":
                    await get_meta_ads_client(settings).send_conversion(hashed)
                else:
                    await get_google_ads_client(settings=settings).import_offline_conversion(hashed)
            except Exception as exc:  # noqa: BLE001 — record + continue (one bad send can't stall the rest)
                await ads_repo.mark_conversion_failed(
                    session, conversion_id=conv["id"], error=str(exc)[:500]
                )
                conversions_failed += 1
                continue
            await ads_repo.mark_conversion_sent(session, conversion_id=conv["id"])
            conversions_sent += 1

    return {
        "campaigns_synced": campaigns_synced,
        "conversions_sent": conversions_sent,
        "conversions_failed": conversions_failed,
    }


async def record_campaign_from_action(
    *, action_id: uuid.UUID, platform: str, name: str, result: dict,
    template_id: uuid.UUID | None = None, ad_account_id: uuid.UUID | None = None,
    daily_budget_cents: int = 0, lifetime_cap_cents: int = 0,
) -> dict | None:
    """Persist the local ``ad_campaigns`` row after an ``ads.create_campaign`` action executed.

    Called by the route once the gate's execute succeeded — binds our local record to the platform's
    returned ids (PAUSED). Operator-scoped; idempotent inserts are the caller's concern. Returns the row.
    """
    external_ref = result.get("external_ref")
    external_ids = result.get("created") if isinstance(result.get("created"), dict) else {}
    async with operator_session() as session:
        return await ads_repo.create_campaign_row(
            session,
            platform=platform,
            name=name,
            template_id=template_id,
            ad_account_id=ad_account_id,
            status="paused",
            daily_budget_cents=daily_budget_cents,
            lifetime_cap_cents=lifetime_cap_cents,
            external_campaign_id=str(external_ref) if external_ref else None,
            external_ids=external_ids or {},
        )
