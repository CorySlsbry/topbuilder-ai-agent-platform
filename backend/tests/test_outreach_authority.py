"""The outreach param-trust fix (migration 0027): compliance facts come ONLY from the authoritative
store — proposer-supplied consent/country/suppression flags are ignored, unresolvable contacts are
HELD, and the warm-up daily cap is enforced at execute time against the send ledger.

Pure tests: the decision matrix (`authoritative_send_decision`) needs no DB; the executor-level
proofs stub the repository + session so the spoof attempt runs the REAL executor code path.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest

from app.actions.executors import ActionError, execute
from app.config import Settings
from app.outreach.compliance import ALLOW, HOLD, authoritative_send_decision

CONSENT_REQUIRED = {"CA", "GB", "DE", "FR"}
BLOCKED = {"CA"}


def _decide(resolved, *, suppressed=False):
    return authoritative_send_decision(
        resolved, contact_id="c-1", email="p@example.com", suppressed=suppressed,
        consent_required_countries=CONSENT_REQUIRED, blocked_countries=BLOCKED,
    )


def test_unresolvable_contact_is_held():
    d = _decide(None)
    assert (d.decision, d.reason) == (HOLD, "contact_unresolved")


def test_suppression_list_hit_is_held_even_with_a_clean_contact_record():
    d = _decide({"country": "US", "consent": True}, suppressed=True)
    assert (d.decision, d.reason) == (HOLD, "suppressed_listed")


def test_blocked_country_held_even_with_recorded_consent():
    d = _decide({"country": "CA", "consent": True})
    assert d.decision == HOLD and d.reason.startswith("country_blocked")


def test_cold_us_contact_is_allowed_and_unknown_country_is_held():
    assert _decide({"country": "US", "consent": False}).decision == ALLOW
    assert _decide({"country": None, "consent": False}).reason == "cold_unknown_jurisdiction"


def test_recorded_unsubscribe_or_bounce_is_held():
    assert _decide({"country": "US", "consent": True, "unsubscribed": True}).decision == HOLD
    assert _decide({"country": "US", "consent": True, "bounced": True}).decision == HOLD


# ---- executor-level: the spoof attempt runs the real code path -------------------------------

def _settings() -> Settings:
    return Settings(
        env="dev",
        jwt_secret="x" * 40,
        outreach_physical_address="123 Main St, Eagle Mountain, UT",
        email_send_mode="fixture",
    )


def _params(**over) -> dict:
    p = {
        "to_email": "prospect@example.com",
        "contact_id": "c-42",
        "subject": "Hello",
        "html": "<p>hi</p>",
        "text": "hi",
        "unsubscribe_url": "https://topbuilderai.com/u/tok123",
        "_tenant_id": str(uuid.uuid4()),
        # THE SPOOF: proposer claims full consent + a safe country + no suppression.
        "consent": True,
        "country": "US",
        "unsubscribed": False,
        "bounced": False,
    }
    p.update(over)
    return p


@pytest.fixture()
def stub_store(monkeypatch):
    """Stub the authority store: session is a no-op; repo facts are controlled per-test."""
    state = {
        "resolved": None, "suppressed": False, "sent_today": 0, "first_send": None,
        "recorded": [],
    }

    @asynccontextmanager
    async def fake_session(_tenant):
        yield object()

    async def resolve_contact(_s, *, email_normalized):
        return state["resolved"]

    async def is_suppressed(_s, *, email_normalized):
        return state["suppressed"]

    async def sent_today_count(_s, *, subdomain):
        return state["sent_today"]

    async def first_send_at(_s, *, subdomain):
        return state["first_send"]

    async def record_send(_s, **kw):
        state["recorded"].append(kw)

    import app.db as db_mod
    import app.repositories.outreach as repo

    monkeypatch.setattr(db_mod, "tenant_session", fake_session)
    monkeypatch.setattr(repo, "resolve_contact", resolve_contact)
    monkeypatch.setattr(repo, "is_suppressed", is_suppressed)
    monkeypatch.setattr(repo, "sent_today_count", sent_today_count)
    monkeypatch.setattr(repo, "first_send_at", first_send_at)
    monkeypatch.setattr(repo, "record_send", record_send)
    return state


async def test_spoofed_consent_params_are_ignored_when_contact_unresolved(stub_store):
    # Proposer claims consent=True/country=US, but the authority store has NO record -> HELD.
    with pytest.raises(ActionError, match="contact_unresolved"):
        await execute("send_outreach_email", _params(), _settings())


async def test_spoofed_params_cannot_unsuppress_a_listed_contact(stub_store):
    stub_store["suppressed"] = True
    stub_store["resolved"] = {"country": "US", "consent": True}
    with pytest.raises(ActionError, match="suppressed_listed"):
        await execute("send_outreach_email", _params(), _settings())


async def test_authoritative_canada_contact_held_despite_params_saying_us(stub_store):
    stub_store["resolved"] = {"country": "CA", "consent": True}
    with pytest.raises(ActionError, match="country_blocked"):
        await execute("send_outreach_email", _params(country="US"), _settings())


async def test_warmup_cap_blocks_the_nth_plus_one_send(stub_store):
    stub_store["resolved"] = {"country": "US", "consent": True}
    stub_store["sent_today"] = 20  # day-0 cap is outreach_warmup_start = 20
    with pytest.raises(ActionError, match="warm-up daily cap"):
        await execute("send_outreach_email", _params(), _settings())


async def test_allowed_send_goes_out_in_fixture_mode_and_is_ledgered(stub_store):
    stub_store["resolved"] = {"country": "US", "consent": False}  # cold US = CAN-SPAM permitted
    res = await execute("send_outreach_email", _params(), _settings())
    assert res["status"] in {"sent", "simulated"} and res["send_ledger"] == "recorded"
    assert stub_store["recorded"] and stub_store["recorded"][0]["subdomain"] == "send.topbuilderai.com"


async def test_missing_contact_id_or_tenant_context_is_refused(stub_store):
    with pytest.raises(ActionError, match="contact_id"):
        await execute("send_outreach_email", _params(contact_id=None), _settings())
    with pytest.raises(ActionError, match="tenant context"):
        await execute("send_outreach_email", _params(_tenant_id=None), _settings())


async def test_off_domain_unsubscribe_url_is_refused(stub_store):
    stub_store["resolved"] = {"country": "US", "consent": True}
    with pytest.raises(ActionError, match="unsubscribe_url must be on"):
        await execute(
            "send_outreach_email",
            _params(unsubscribe_url="https://evil.example.com/unsub"),
            _settings(),
        )
