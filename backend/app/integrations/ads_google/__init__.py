"""Google Ads adapter (Ads-CRM, ADR 0009) — operator-scoped ad-platform integration.

Two modules, mirroring the house adapter shape:
  * :mod:`app.integrations.ads_google.client` — the ``GoogleAdsClient`` Protocol + a config-driven
    factory. ``ads_mode!='live'`` returns a deterministic FIXTURE client (offline, hand-checkable ids);
    ``ads_mode='live'`` returns a typed skeleton that FAILS CLOSED (raises, never fabricates a success).
  * :mod:`app.integrations.ads_google.google_ads_oauth` — Authorization-Code + PKCE token exchange,
    mirroring ``app.integrations.google.google_oauth`` (``access_type=offline`` + ``prompt=consent`` so
    Google returns a refresh token) and ADDING PKCE (``code_challenge``/``code_verifier`` S256).

POSTURE (load-bearing): money/ids never come from the LLM (ADR 0003); every ad-platform WRITE goes
through the propose→approve→execute action gate (ADR 0007) — this adapter is only the platform boundary.
"""
from __future__ import annotations
