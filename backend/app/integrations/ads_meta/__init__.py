"""Meta (Facebook / Instagram) Ads adapter — operator-only ad-platform integration (ADR 0009).

The pure deterministic engine (``app/ads/engine.py``) assembles a platform-ready :class:`CampaignPlan`
with the PAUSED-on-create request payloads; THIS adapter is the I/O boundary that talks to the Meta
Marketing API + Conversions API. It is fail-closed and fixture-first exactly like every other
integration here:

  * ``ads_mode='fixture'`` (default) -> :class:`FixtureMetaAdsClient` returns deterministic ids +
    canned insights, fully offline, so the whole module is testable with NO live API.
  * ``ads_mode='live'`` -> :class:`LiveMetaAdsClient`, a fail-closed skeleton: every WRITE RAISES
    rather than fabricate a success (ADR 0003 / ADR 0007 — no parallel write path; real writes flow
    propose->approve->execute through the action gate once wired).

OAuth is OPERATOR-scoped with PKCE (``meta_oauth.py``); tokens live ONLY in the operator credential
vault (``operator_credentials``, migration 0023), never in app config.
"""
from __future__ import annotations
