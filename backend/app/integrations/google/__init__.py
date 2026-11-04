"""Google Workspace adapters (Drive / Sheets) — per-customer OAuth connection.

The platform is provider-agnostic: agents consume CANONICAL domain models, and each external system
maps onto them through an adapter. Google connects a customer's Drive + Sheets so the Financial agent
can read their AR-tracker sheet and budget-to-actual doc directly (replacing the manual share + Zapier
path some tenants — e.g. Alex's, who uses LiveFlow today — run by hand).

The connection is established with the standard Authorization-Code OAuth2 flow, mirroring the proven
Procore onboarding exactly (`app/integrations/construction/procore_oauth.py`): the customer admin
starts the flow, grants access in Google's consent screen, and Google redirects back to
``/v1/integrations/google/callback`` with a one-time ``code`` that we exchange server-side for tokens.
We persist the long-lived ``refresh_token`` ENCRYPTED in the per-tenant AES-256-GCM vault. The
tenant-bound HMAC ``state`` (CSRF + tenant binding) is the shared, provider-agnostic
`app/integrations/construction/oauth_state.py` — NOT duplicated here.
"""
from __future__ import annotations
