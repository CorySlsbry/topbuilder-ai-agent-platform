# Ads-CRM Integration Go-Live — Meta + Google Ads

The Admin Ads-CRM (ADR 0009) ships fully built and **offline** (`ADS_MODE=fixture`): the engine,
executors, CRM, OAuth, and routes all run and test with **no live ad API**. Going live is a set of
**external approvals only you (Cory, the platform operator) can complete**, plus a config flip — not a
code change. This doc is the checklist of those external gates.

## The load-bearing safety guarantee (don't skip the meaning of "fixture")

In `ADS_MODE=fixture` the platform **cannot** touch Meta or Google — it returns deterministic synthetic
ids and metrics. In `ADS_MODE=live` the live adapter **fails closed**: until each real write is wired and
verified against a real ad account, the executor **raises** rather than fabricating a success. A campaign
can never be reported as launched, a budget as changed, or a conversion as sent, when it wasn't. So the
order is always: get the approvals → flip the mode → verify each live call against a real account → only
then trust a "launched" result.

Everything that spends money runs through the **action gate** (ADR 0007): `propose → approve → execute`,
**create-PAUSED**, with `ads.create_campaign` / `ads.update_budget` / `ads.activate_campaign` requiring a
**2FA admin (aal2)** approval and being **ALWAYS-HITL** (an `auto` agent queues them, never self-fires).
`ads.activate_campaign` is the only step that starts spend, and it is separately approvable.

---

## 1. Meta (Facebook / Instagram) — your external gates

These are completed in Meta's Business / Developer portals under the operator's business account. None of
them can be faked in code.

- [ ] **Meta App** created in the Meta for Developers portal (a Business-type app). Capture the
      **App ID** and **App Secret**.
- [ ] **Business verification** completed on the Meta Business account that owns the app (legal entity
      docs). Required before the Marketing API permissions can be granted in production.
- [ ] **App Review — Advanced Access** approved for the permissions the engine uses:
      `ads_management`, `ads_read`, `business_management`, `leads_retrieval`. Standard Access is
      dev-only / your own assets; production campaign management on a real account needs Advanced Access.
- [ ] **Redirect URI** registered on the app's Facebook Login settings, exactly matching
      `META_REDIRECT_URI` (`https://api.<domain>/v1/integrations/meta/callback`).
- [ ] **Conversions API (CAPI):** create / locate the **Pixel** → capture the **Pixel ID**; generate a
      **CAPI access token** (server-events) → store as `META_CAPI_TOKEN`. (The Pixel ID is also injected
      client-side on the show pages, env-gated, in Phase 2.)
- [ ] Confirm the **API version** in use (`META_API_VERSION`, currently `v21.0`) is still supported on
      your go-live date; bump if Meta has deprecated it.

## 2. Google Ads — your external gates

- [ ] **Google Ads Developer Token** requested and **approved** (Basic or Standard access) from your
      Google Ads manager account. **Required for ANY live Google Ads API call** — Test-account access
      can develop, but real-account writes need an approved token. This is the longest-lead item; start it
      first.
- [ ] **Google Cloud OAuth client** (Web application) created → capture **Client ID + Client Secret**.
      Add the redirect URI `https://api.<domain>/v1/integrations/google_ads/callback` (matches
      `GOOGLE_ADS_REDIRECT_URI`). The OAuth consent screen must request the `adwords` scope.
- [ ] **(Optional) MCC / manager account** — if you manage the ad account under a manager (MCC), capture
      the **login-customer-id** (digits only) → `GOOGLE_ADS_LOGIN_CUSTOMER_ID`.
- [ ] **Conversion action** created in Google Ads for offline/enhanced conversion import → capture its id
      → `GOOGLE_ADS_CONVERSION_ACTION_ID`.
- [ ] **(Optional) GA4 / gtag** measurement id for the show pages' client-side tag → `GOOGLE_TAG_ID`.

## 3. Secrets (Secret Manager only — never code or `.env` in the image)

Add these to Secret Manager and mount them to the API service. Nothing here is a code change; the app
reads them from the environment.

| Secret / env | Holds | Source |
|---|---|---|
| `META_APP_ID` | Meta app id | §1 |
| `META_APP_SECRET` | Meta app secret | §1 |
| `META_REDIRECT_URI` | `https://api.<domain>/v1/integrations/meta/callback` | your domain |
| `META_PIXEL_ID` | Pixel id (CAPI + show pages) | §1 |
| `META_CAPI_TOKEN` | Conversions API server token | §1 |
| `GOOGLE_ADS_CLIENT_ID` | OAuth client id | §2 |
| `GOOGLE_ADS_CLIENT_SECRET` | OAuth client secret | §2 |
| `GOOGLE_ADS_REDIRECT_URI` | `https://api.<domain>/v1/integrations/google_ads/callback` | your domain |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Approved developer token | §2 |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | MCC id (optional) | §2 |
| `GOOGLE_ADS_CONVERSION_ACTION_ID` | Offline/enhanced conversion target | §2 |
| `GOOGLE_TAG_ID` | GA4/gtag id (optional, show pages) | §2 |
| `CREDENTIAL_ENCRYPTION_KEY` | AES-256-GCM vault key (already set for the rest of the app) | existing |
| `PLATFORM_OPERATOR_EMAILS` | Your operator email(s) — without this, every Ads-CRM route 403s | you |

Tokens obtained via the connect flow are **never** put in config — they are encrypted into the operator
vault (`operator_credentials`, AES-256-GCM) at `/callback`. The client id/secret/developer-token above are
the only ad-platform secrets that live in Secret Manager; the per-account access/refresh tokens live in the
vault and are covered by `scripts/rotate_credentials.py`.

## 4. The env flips (config, not code)

Set on the API service via Secret Manager / env (mirrors `docs/GO_LIVE_RUNBOOK.md`):

- `ENV=prod`
- `AUTH_MODE=jwks` (or `supabase`) — operator identity verified by the IdP; **dev HS256 tokens are
  rejected outside dev**, so real 2FA (aal2) is enforced. The dev god-token's hardcoded aal2 only applies
  under `ENV=dev`.
- `PLATFORM_OPERATOR_EMAILS=<your operator email(s)>` — fail-closed empty by default; **must** be set or
  every `/v1/crm` + `/v1/ads` route 403s for everyone (intended).
- `ADS_MODE=live` — flips Meta/Google clients from fixture to the live (fail-closed) adapters.
- `ACTIONS_ENABLED=true` — the master switch for the write path; the five `ads.*` kinds are already in
  `ACTIONS_ALLOWED_KINDS`. Set this **only** after the operator autonomy posture is intentional (the
  money-committing ads kinds stay ALWAYS-HITL regardless).
- Lock `ALLOWED_ORIGINS` / `TRUSTED_HOSTS` to the deployed origins.

## 5. Go-live order + verification (the gate — clear ALL before trusting a live launch)

1. [ ] Meta App Review + Business verification **approved**; Google Ads developer token **approved**.
       (These gate everything; do them first.)
2. [ ] All §3 secrets in Secret Manager and mounted; `PLATFORM_OPERATOR_EMAILS` set; redirect URIs match.
3. [ ] **Connect each platform:** as a 2FA operator, hit `/v1/integrations/meta/connect` and
       `/v1/integrations/google_ads/connect`, complete consent. Confirm a row lands in
       `operator_credentials` and `ad_accounts.status='connected'` with `vault_credential_id` set.
       (PKCE + HttpOnly session cookie must round-trip; a mismatch 400s.)
4. [ ] Flip `ADS_MODE=live` + `ACTIONS_ENABLED=true`; deploy; smoke every router.
5. [ ] **One create end-to-end on a real account, PAUSED:** `propose` `ads.create_campaign` → `approve`
       (2FA) → `execute`. Confirm the real platform campaign exists and is **PAUSED**, and `ad_campaigns`
       holds the `external_ref`. Then `undo` it and confirm the platform-side teardown. (This proves the
       live write is wired and reversible **without** spending.)
6. [ ] **One activate** on a throwaway campaign with a tiny budget → confirm spend starts, then
       `ads.pause_campaign` → confirm it stops. Verify `ad_metrics` ingests at least one day.
7. [ ] **One conversion** through `ads.sync_conversion` with **hashed** PII (verify the payload in
       `conversion_syncs` is the SHA-256 hex, never plaintext) → confirm the platform receipt and that a
       duplicate send is deduped by `UNIQUE (platform, dedupe_key)`.
8. [ ] Confirm `scripts/rotate_credentials.py` includes `operator_credentials` so a key rotation reaches
       ad tokens.

Only after 1–8 pass on real accounts should an ad campaign's autonomy be relied on — and even then the
money-committing kinds remain human-approved (ALWAYS-HITL) by design.
