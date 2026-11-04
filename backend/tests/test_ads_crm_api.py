"""End-to-end DB-integration tests for the Ads-CRM layer (ADR 0009).

Proves the load-bearing guarantees against a real Postgres + RLS:

  * RLS 2-context — rows seeded under ``operator_session()`` are visible to an operator session and
    INVISIBLE to a ``tenant_session`` (``app.operator`` unset → the operator-only policy fails closed).
  * The action gate for ad SPEND — ``ads.create_campaign`` runs propose → approve → execute through the
    shared human-approved gate (NEVER a parallel write path). Execute produces a fixture PAUSED campaign
    with a stable ``external_ref``; re-execute is idempotent; undo compensates (pauses for teardown).
  * Idempotent ingest dedupe — re-ingesting the same email upserts ONE contact (no duplicate).
  * Conversion-sync dedupe — the same ``(platform, dedupe_key)`` is queued exactly once.
  * Operator authz — a non-operator (admin whose email is NOT on the allowlist) gets 403 on a /v1/crm
    route, even with a valid admin+aal2 dev-token.

Plus a fixture E2E: seed the Nashville geofence template + a Meta ad account → build (propose) →
approve → execute (PAUSED ``ad_campaigns`` row, ``external_ref`` present) → sync metrics onto the row →
a booked lead creates a SHA-256-hashed conversion_sync.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from app.ads import seed as ads_seed
from app.ads import service as ads_service
from app.ads.pii import hash_email, hash_phone
from app.config import Settings
from app.db import operator_session, tenant_session
from app.demo import DEMO_TENANTS
from app.repositories import ads as ads_repo
from app.repositories import crm
from app.security import Principal

pytestmark = pytest.mark.integration

# The apex admin's email is what the apex dev-token carries; we make it a platform operator below.
_APEX = DEMO_TENANTS["apex"]
_OPERATOR_EMAIL = _APEX.admin_email
_OPERATOR_SETTINGS = Settings(platform_operator_emails=_OPERATOR_EMAIL)
# Fixture, action-gate-on settings the execute step uses (ads.create_campaign on the allowlist).
_EXEC_SETTINGS = Settings(
    actions_enabled=True,
    ads_mode="fixture",
    actions_allowed_kinds="ads.create_campaign",
)
_NASHVILLE_SLUG = "build-expo-nashville-2026"
# Independent oracle for the fixture create result (FixtureMetaAdsClient slugs plan.name).
_NASHVILLE_NAME = "Build Expo Nashville 2026 — Geofence"
_NASHVILLE_REF = "meta-camp-build-expo-nashville-2026-geofence"


async def _operator_token(client: AsyncClient, slug: str = "apex") -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug, "role": "admin"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _patch_operator_gate(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    """Point the CRM + Ads route operator gates (and config) at ``settings`` (the allowlist)."""
    from app import config
    from app.api import routes_ads, routes_crm

    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(routes_crm, "get_settings", lambda: settings)
    monkeypatch.setattr(routes_ads, "get_settings", lambda: settings)


async def _wipe_operator_tables() -> None:
    """Clear the operator Ads-CRM tables so RLS-count + dedupe assertions are deterministic.

    The session conftest truncates only TENANT tables; these operator tables carry no tenant_id and
    are not in that list, so we clear them here under an operator session (RLS grants the delete).
    """
    async with operator_session() as session:
        from sqlalchemy import text

        for table in (
            "conversion_syncs", "ad_metrics", "ad_campaigns", "ad_campaign_templates",
            "crm_activities", "crm_leads", "crm_contacts", "ad_accounts", "operator_credentials",
        ):
            await session.execute(text(f"DELETE FROM {table}"))


async def _seed_meta_account() -> dict:
    async with operator_session() as session:
        return await ads_repo.upsert_ad_account(
            session,
            platform="meta",
            external_account_id="act_555000111",
            display_name="Top Builder AI — Meta",
            status="connected",
        )


async def _seed_nashville_template() -> dict:
    async with operator_session() as session:
        rows = await ads_seed.seed_templates(session)
    return next(t for t in rows if t["slug"] == _NASHVILLE_SLUG)


async def _principal() -> Principal:
    return Principal(
        tenant_id=_APEX.tenant_id, user_id=_APEX.admin_user_id, email=_OPERATOR_EMAIL,
        role="admin", aal="aal2",
    )


@pytest.fixture
async def _dispose_engine():
    yield
    from app import db

    await db.get_engine().dispose()
    db.get_engine.cache_clear()
    db.get_sessionmaker.cache_clear()


# ── RLS 2-context ───────────────────────────────────────────────────────────────────────────────────
async def test_operator_rows_are_invisible_to_a_tenant_session(_dispose_engine) -> None:
    """Rows seeded under operator_session are seen by operators and ZERO under a tenant_session."""
    await _wipe_operator_tables()

    async with operator_session() as session:
        ingest = await crm.ingest_lead(session, email="person1@example.com", source="manual")
        account = await ads_repo.upsert_ad_account(
            session, platform="meta", external_account_id="act_iso_1", status="connected"
        )
        await ads_repo.create_campaign_row(
            session, platform="meta", name="Isolation Probe", ad_account_id=account["id"],
            status="paused",
        )

    # Operator session sees the seeded rows.
    async with operator_session() as session:
        leads = await crm.list_leads(session)
        campaigns = await ads_repo.list_campaigns(session)
    assert any(l["id"] == ingest["lead"]["id"] for l in leads)
    assert len(campaigns) == 1

    # A tenant session (app.operator unset) sees ZERO rows — the operator-only policy fails closed.
    from sqlalchemy import text

    async with tenant_session(_APEX.tenant_id) as session:
        lead_count = (await session.execute(text("SELECT count(*) FROM crm_leads"))).scalar_one()
        campaign_count = (await session.execute(text("SELECT count(*) FROM ad_campaigns"))).scalar_one()
    assert lead_count == 0
    assert campaign_count == 0


# ── lead ingest + conversion dedupe (repo layer) ─────────────────────────────────────────────────────
async def test_lead_ingest_and_conversion_sync_dedupe(_dispose_engine) -> None:
    await _wipe_operator_tables()
    async with operator_session() as session:
        first = await crm.ingest_lead(
            session, email="person2@example.com", full_name="Pat Owner", source="landing"
        )
        # Re-ingest the SAME email: upserts ONE contact (dedupe by email), not two.
        second = await crm.ingest_lead(
            session, email="person2@example.com", company="Summit Mechanical", source="landing"
        )
        assert second["contact"]["id"] == first["contact"]["id"]
        assert second["contact"]["company"] == "Summit Mechanical"  # enriched, not clobbered

        # Conversion dedupe: the same (platform, dedupe_key) queues exactly once.
        c1 = await ads_repo.create_conversion_sync(
            session, platform="meta", event_name="Lead", dedupe_key="lead-xyz",
            lead_id=first["lead"]["id"], payload={"em": hash_email("person2@example.com")},
        )
        c2 = await ads_repo.create_conversion_sync(
            session, platform="meta", event_name="Lead", dedupe_key="lead-xyz",
            lead_id=first["lead"]["id"], payload={"em": hash_email("person2@example.com")},
        )
        assert c1 is not None
        assert c2 is None  # ON CONFLICT (platform, dedupe_key) DO NOTHING

        pending = await ads_repo.list_pending_conversion_syncs(session, platform="meta")
    assert len([p for p in pending if p["dedupe_key"] == "lead-xyz"]) == 1


# ── operator authz (HTTP 403 for a non-operator) ─────────────────────────────────────────────────────
async def test_non_operator_admin_gets_403_on_crm_route(
    monkeypatch: pytest.MonkeyPatch, _dispose_engine
) -> None:
    """A valid admin+aal2 dev-token whose email is NOT on the allowlist is denied the operator surface."""
    from app.main import app

    # Allowlist holds a DIFFERENT email, so the apex admin token is admin+aal2 but NOT an operator.
    _patch_operator_gate(monkeypatch, Settings(platform_operator_emails="someone-else@topbuilderai.com"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _operator_token(client, "apex")
        resp = await client.get("/v1/crm/leads", headers=headers)
    assert resp.status_code == 403, resp.text


# ── the action gate: propose -> approve -> execute -> idempotent -> undo ──────────────────────────────
async def test_ads_create_campaign_gate_flow(
    monkeypatch: pytest.MonkeyPatch, _dispose_engine
) -> None:
    await _wipe_operator_tables()
    account = await _seed_meta_account()
    template = await _seed_nashville_template()
    principal = await _principal()

    # Propose ads.create_campaign through the gate (nothing written to a platform yet).
    proposed = await ads_service.plan_and_propose(principal, account=account, template=template)
    assert proposed["status"] == "proposed"
    assert proposed["platform"] == "meta"
    assert proposed["daily_budget_cents"] == 1000  # Nashville $10/day (independent oracle from seed)
    assert proposed["lifetime_cap_cents"] == 2000
    action_id = uuid.UUID(proposed["action_id"])

    # Idempotent propose: the same template+account dedupes to the same action.
    again = await ads_service.plan_and_propose(principal, account=account, template=template)
    assert again["action_id"] == proposed["action_id"]

    from app.actions import service as action_service

    # Approve, then execute under fixture + actions-enabled + allowlisted settings.
    monkeypatch.setattr("app.actions.service.get_settings", lambda: _EXEC_SETTINGS)
    approved = await action_service.approve_action(principal, action_id)
    assert approved.status == "approved"

    executed = await action_service.execute_action(principal, action_id)
    assert executed.status == "executed"
    assert executed.result["status"] == "PAUSED"  # PAUSED-on-create (ADR 0007)
    assert executed.result["external_ref"] == _NASHVILLE_REF

    # Idempotent execute: re-execute returns the same external_ref, no second write.
    again_exec = await action_service.execute_action(principal, action_id)
    assert again_exec.result["external_ref"] == executed.result["external_ref"]

    # Undo compensates (pauses for teardown) and is idempotent.
    undone = await action_service.undo_action(principal, action_id)
    assert undone.status == "undone"
    assert (await action_service.undo_action(principal, action_id)).status == "undone"


# ── full fixture E2E ─────────────────────────────────────────────────────────────────────────────────
async def test_fixture_e2e_nashville_build_execute_sync_convert(
    monkeypatch: pytest.MonkeyPatch, _dispose_engine
) -> None:
    """Seed Nashville → build (propose) → approve → execute → record PAUSED row → sync metrics →
    a booked lead creates a hashed conversion_sync."""
    await _wipe_operator_tables()
    account = await _seed_meta_account()
    template = await _seed_nashville_template()
    principal = await _principal()

    proposed = await ads_service.plan_and_propose(principal, account=account, template=template)
    action_id = uuid.UUID(proposed["action_id"])

    from app.actions import service as action_service

    monkeypatch.setattr("app.actions.service.get_settings", lambda: _EXEC_SETTINGS)
    await action_service.approve_action(principal, action_id)
    executed = await action_service.execute_action(principal, action_id)

    # Record the local PAUSED ad_campaigns row from the executed action's result.
    campaign = await ads_service.record_campaign_from_action(
        action_id=action_id,
        platform="meta",
        name=_NASHVILLE_NAME,
        result=executed.result,
        template_id=template["id"],
        ad_account_id=account["id"],
        daily_budget_cents=proposed["daily_budget_cents"],
        lifetime_cap_cents=proposed["lifetime_cap_cents"],
    )
    assert campaign is not None
    assert campaign["status"] == "paused"
    assert campaign["external_campaign_id"] == _NASHVILLE_REF

    # Sync metrics: the fixture Meta insights (spend 4200c, 23 leads) roll onto the campaign + ad_metrics.
    summary = await ads_service.sync(_EXEC_SETTINGS, day=date(2026, 6, 22))
    assert summary["campaigns_synced"] == 1

    async with operator_session() as session:
        synced = await ads_repo.get_campaign(session, campaign_id=campaign["id"])
        metrics = await ads_repo.list_metrics(session, campaign_id=campaign["id"])
    assert synced["spend_cents"] == 4200  # fixture insight oracle
    assert len(metrics) == 1
    assert metrics[0]["leads"] == 23

    # A booked lead → a SHA-256-hashed conversion_sync (PII never stored plaintext).
    async with operator_session() as session:
        ingest = await crm.ingest_lead(
            session, email="person3@example.com", phone="+1 (250) 555-0142",
            full_name="Sam Contractor", company="Summit Heat Pumps", source="meta_ads",
        )
        await crm.set_stage(session, lead_id=ingest["lead"]["id"], stage="booked")
        conv = await ads_repo.create_conversion_sync(
            session,
            platform="meta",
            event_name="Lead",
            dedupe_key=f"booked-{ingest['lead']['id']}",
            lead_id=ingest["lead"]["id"],
            payload={
                "em": hash_email("person3@example.com"),
                "ph": hash_phone("+1 (250) 555-0142"),
            },
        )
    assert conv is not None
    # The payload carries ONLY hashes — independent oracle: 64-char lowercase hex, never the plaintext.
    em_hash = conv["payload"]["em"]
    assert em_hash == hash_email("person3@example.com")
    assert len(em_hash) == 64 and em_hash == em_hash.lower()
    assert "person3@example.com" not in str(conv["payload"])
