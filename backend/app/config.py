"""Typed application settings, loaded from environment / .env (see .env.example)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # runtime
    env: str = "dev"
    log_level: str = "INFO"
    api_port: int = 8000

    # database — see ADR 0002 for why there are two URLs
    database_url: str = "postgresql+asyncpg://app_user:app_pw@localhost:5432/fieldops"
    migration_database_url: str = "postgresql://postgres:postgres@localhost:5432/fieldops"
    # Remote DB connections are pinned to TLS 1.2 minimum (encryption in transit). Default is
    # encrypt-only; flip to true to require full CA/hostname validation once the pooler CA is pinned.
    db_ssl_verify: bool = False

    # auth / jwt
    jwt_secret: str = "change-me"
    jwt_issuer: str = "fieldops-iq"
    jwt_audience: str = "fieldops-api"
    jwt_expiry_minutes: int = 60

    # llm reasoning layer
    anthropic_api_key: str | None = None
    workforce_reasoning_model: str = "claude-sonnet-4-6"
    disable_llm: bool = False
    # opt-in zero-data-retention header for LLM calls (Anthropic account-level entitlement; default
    # OFF / no-op — only send it once the account is actually entitled). See app/assistant/llm_client.py.
    anthropic_zero_retention: bool = False

    # in-app assistant (independent of disable_llm, which governs run narration only): needs the
    # Anthropic key; capped per tenant per day so a public demo can't burn tokens
    assistant_model: str = "claude-sonnet-4-6"
    assistant_daily_limit: int = 150
    assistant_max_tool_rounds: int = 6
    assistant_daily_limit_per_ip: int = 30  # DB-backed per-IP sub-cap (denial-of-wallet / griefing)
    assistant_daily_limit_global: int = 2000  # DB-backed global ceiling across all callers

    # ingest cost guardrails (per tenant per day) — embeddings can be a real spend at go-live
    feedback_daily_limit: int = 500
    knowledge_ingest_daily_limit: int = 200
    knowledge_max_embed_chars: int = 200_000  # clamp the text actually embedded per document
    url_fetch_max_bytes: int = 5_000_000  # cap a fetched URL body (SSRF/DoS)

    # learning governance — auto-approving a learned rule removes the human backstop, so it is a
    # DEPLOY decision, never a tenant-settable param (SEC-3). Default: human approval is mandatory.
    learning_auto_approve_enabled: bool = False

    # servicetitan adapter
    servicetitan_mode: str = "fixture"  # fixture | live
    servicetitan_client_id: str | None = None
    servicetitan_client_secret: str | None = None
    servicetitan_app_key: str | None = None
    servicetitan_tenant_id: str | None = None
    servicetitan_base_url: str = "https://api.servicetitan.io"
    servicetitan_auth_url: str = "https://auth.servicetitan.io/connect/token"

    # construction adapters (Buildertrend, Procore) — serve jobs/documents/accounting only.
    # Fail-closed live skeletons, exactly like ServiceTitan's (ADR 0005); fixture by default.
    buildertrend_mode: str = "fixture"  # fixture | live
    buildertrend_api_key: str | None = None
    buildertrend_partner_token: str | None = None  # partner-program issued; live API partner-gated
    buildertrend_base_url: str = "https://api.buildertrend.com"
    procore_mode: str = "fixture"  # fixture | live
    procore_client_id: str | None = None
    procore_client_secret: str | None = None
    procore_refresh_token: str | None = None  # from the marketplace OAuth2 install (rotates on use)
    procore_company_id: str | None = None
    procore_base_url: str = "https://api.procore.com"
    procore_auth_url: str = "https://login.procore.com/oauth/token"
    procore_authorize_url: str = "https://login.procore.com/oauth/authorize"
    # Development Sandbox uses https://sandbox.procore.com for BOTH oauth + api (its own client id/secret,
    # company 4285693). Override base_url/auth_url/authorize_url to the sandbox host when PROCORE_MODE=live
    # against the dev sandbox. oob = redirectless bootstrap; the per-customer prod flow uses the /callback.
    procore_redirect_uri: str = "urn:ietf:wg:oauth:2.0:oob"

    # Google Workspace (Drive / Sheets) — per-customer Authorization-Code OAuth, mirroring Procore.
    # The customer admin connects their Drive + Sheets so the Financial agent can read their AR-tracker
    # sheet + budget-to-actual doc directly. The long-lived refresh_token is encrypted in the vault
    # (provider="google"); we never store the client_secret in the DB. Scopes start read-only.
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None  # e.g. https://api.example.com/v1/integrations/google/callback
    # Space-delimited OAuth scopes requested at consent. Read-only Drive + Sheets to start; userinfo.email
    # lets us label the connection with the connecting account (best-effort).
    google_scopes: str = (
        "https://www.googleapis.com/auth/drive.readonly "
        "https://www.googleapis.com/auth/spreadsheets.readonly "
        "https://www.googleapis.com/auth/userinfo.email"
    )
    google_authorize_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_url: str = "https://oauth2.googleapis.com/token"
    google_userinfo_url: str = "https://www.googleapis.com/oauth2/v3/userinfo"

    # ── Ads-CRM (ADR 0009): operator-only ad-platform integration. Fixture by default; live FAILS CLOSED.
    # One mode gate for both platforms; fixture returns deterministic ids so the whole module is testable
    # with NO live API. ad-platform OAuth is OPERATOR-scoped (PKCE + state->server-session) and tokens go
    # in the operator credential vault (operator_credentials, migration 0023), never in app config.
    ads_mode: str = "fixture"  # fixture | live
    # Meta (Facebook/Instagram) Ads — Marketing API + Conversions API.
    meta_app_id: str | None = None
    meta_app_secret: str | None = None
    meta_redirect_uri: str | None = None  # https://api.../v1/integrations/meta/callback
    meta_scopes: str = "ads_management,ads_read,business_management,leads_retrieval"
    meta_api_version: str = "v21.0"
    meta_authorize_url: str = "https://www.facebook.com/v21.0/dialog/oauth"
    meta_token_url: str = "https://graph.facebook.com/v21.0/oauth/access_token"
    meta_graph_base: str = "https://graph.facebook.com/v21.0"
    meta_pixel_id: str | None = None     # website pixel + Conversions API target
    meta_capi_token: str | None = None   # Conversions API access token (server events)
    # Google Ads — Google Ads API. OAuth + an APPROVED developer token (basic/standard access) + opt. MCC.
    google_ads_client_id: str | None = None
    google_ads_client_secret: str | None = None
    google_ads_redirect_uri: str | None = None
    google_ads_scopes: str = "https://www.googleapis.com/auth/adwords"
    google_ads_developer_token: str | None = None      # Google-approved; required for ANY live call
    google_ads_login_customer_id: str | None = None    # MCC id (optional), digits only
    google_ads_authorize_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_ads_token_url: str = "https://oauth2.googleapis.com/token"
    google_ads_api_base: str = "https://googleads.googleapis.com/v18"
    google_ads_conversion_action_id: str | None = None  # offline/enhanced conversion import target
    google_tag_id: str | None = None     # gtag/GA4 measurement id for the show pages (client-side)

    # auth — `dev` uses the local HS256 issuer; `jwks` verifies an external OIDC IdP
    auth_mode: str = "dev"  # dev | jwks | supabase  (dev also accepts Supabase tokens when configured)

    # Supabase Auth (real customer/operator login). Tokens are verified against the project's JWKS
    # (ES256); identity -> tenant/role resolves through the user_memberships directory (migration 0013).
    supabase_url: str | None = None  # https://<ref>.supabase.co
    supabase_anon_key: str | None = None  # publishable; served to the SPA via GET /auth/config
    supabase_audience: str = "authenticated"

    @property
    def supabase_issuer(self) -> str | None:
        return f"{self.supabase_url.rstrip('/')}/auth/v1" if self.supabase_url else None

    @property
    def supabase_jwks_url(self) -> str | None:
        return f"{self.supabase_issuer}/.well-known/jwks.json" if self.supabase_url else None

    @property
    def supabase_auth_configured(self) -> bool:
        return bool(self.supabase_url)
    oidc_jwks_url: str | None = None
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_tenant_claim: str = "tenant_id"
    oidc_role_claim: str = "role"

    # platform operators — emails (comma-separated, lowercased) allowed to administer ANY tenant
    # (cross-tenant membership invites/listing). Empty = no one can target a tenant other than their
    # own through the admin API. A per-tenant 'admin' role is NOT a platform operator.
    platform_operator_emails: str = ""

    # web hardening
    allowed_origins: str = "*"  # comma-separated; lock down in prod
    trusted_hosts: str = "*"  # comma-separated host allowlist
    rate_limit_per_minute: int = 120
    rate_limit_burst: int = 40
    hsts_enabled: bool = False  # enable in prod (behind HTTPS)
    webhook_signing_secret: str | None = None  # HMAC-SHA256 secret for inbound webhooks
    qbo_webhook_verifier_token: str | None = None  # Intuit Verifier Token (QBO intuit-signature, ADR 0010)
    cron_secret: str | None = None  # shared key the scheduled consolidation endpoint requires (X-Cron-Key)

    # credential vault (envelope-encrypt stored ServiceTitan/QBO tokens)
    credential_encryption_key: str | None = None  # urlsafe-base64 32-byte AES-256 key (AES-256-GCM)
    # retired key(s), comma-separated, accepted for DECRYPT-ONLY during a rotation (primary still
    # encrypts). See scripts/rotate_credentials.py + docs/CREDENTIAL_ROTATION.md. Default none.
    credential_encryption_key_old: str | None = None

    # embeddings / RAG
    embedding_provider: str = "openai"  # openai | hashing (hashing = offline/deterministic)
    openai_api_key: str | None = None
    embedding_model: str = "text-embedding-3-large"
    embedding_dim: int = 3072  # must match knowledge_chunks.embedding vector(N)
    rag_top_k: int = 5

    # accounting (Financial agent) — QuickBooks Online via Intuit's OWN OAuth 2.0 (NO Zapier/iPaaS).
    # The customer admin connects their QBO company in Intuit's consent screen; the callback receives
    # code + state + realmId. We exchange the code server-side and encrypt {refresh_token, realm_id}
    # in the per-tenant AES-256-GCM vault (provider="quickbooks"). realm_id is the company id needed on
    # every API call. This mirrors the Procore/Google Authorization-Code flows exactly; the only QBO
    # differences are the extra realmId on the callback and the HTTP-Basic token exchange.
    accounting_mode: str = "fixture"  # fixture | quickbooks
    quickbooks_client_id: str | None = None
    quickbooks_client_secret: str | None = None
    quickbooks_refresh_token: str | None = None
    quickbooks_realm_id: str | None = None
    # Space-delimited OAuth scopes. DECIDED (see docs/QBO_SCOPE_DECISION.md): Accounting API,
    # READ-ONLY — the Financial agent reads AR/AP aging, invoices, balance sheet, P&L. We do NOT
    # request com.intuit.quickbooks.payment or openid (no card processing, no sign-in-with-Intuit),
    # and we do NOT use QBO Payroll (payroll lives in ServiceTitan). Adding either scope would expand
    # the consent surface and is guarded by tests/test_qbo_scope.py — do not widen without updating
    # the decision doc + that guard. LiveFlow's budget-to-actual + trailing-12 P&L is reproduced
    # natively from this QBO P&L via app/org/eos.py (no LiveFlow, no Zapier).
    quickbooks_scopes: str = "com.intuit.quickbooks.accounting"
    # sandbox | production — selects which API base to read from at go-live. The OAuth authorize/token
    # hosts are the SAME for both (Intuit routes by client id); only the API host differs (sandbox-
    # quickbooks.api.intuit.com vs quickbooks.api.intuit.com). Flip base_url accordingly at go-live.
    quickbooks_environment: str = "sandbox"  # sandbox | production
    quickbooks_redirect_uri: str | None = None  # e.g. https://api.example.com/v1/integrations/quickbooks/callback
    quickbooks_base_url: str = "https://quickbooks.api.intuit.com"
    quickbooks_authorize_url: str = "https://appcenter.intuit.com/connect/oauth2"
    quickbooks_token_url: str = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

    # inventory (Inventory agent) — sources from ServiceTitan's inventory module when live
    inventory_mode: str = "fixture"  # fixture | servicetitan

    # booking (24/7 Booking agent) — structured intakes from the voice/telephony provider (ADR 0006).
    # `live` drains intakes from the signed-webhook event_queue and availability from ServiceTitan.
    booking_intake_mode: str = "fixture"  # fixture | live

    # routing / dispatch agent — jobs + technicians source (ServiceTitan when live).
    dispatch_mode: str = "fixture"  # fixture | servicetitan

    # documents agent — inbound documents + known customers (ServiceTitan + OCR when live).
    documents_mode: str = "fixture"  # fixture | servicetitan

    # pricebook agent — the ServiceTitan Pricebook (items + bill of materials + sold-hour labor) plus the
    # vendor cost update feed. ServiceTitan pricebook/v2 is the source of record when live.
    pricebook_mode: str = "fixture"  # fixture | servicetitan

    # collections (A/R Collections agent) — open invoices + aging. QuickBooks AgedReceivableDetail is the
    # reconciled book of record when live (docs/QBO_DATA_MAP §2/§3.1); ServiceTitan AR is a cross-check.
    collections_mode: str = "fixture"  # fixture | quickbooks | servicetitan
    # outbound voice/SMS for dunning — PROVIDER-AGNOSTIC (no Twilio/RingCentral hardcode; assume VoIP).
    # `live` selects the fail-closed LiveVoiceClient skeleton; the provider name is read by the live impl.
    voice_mode: str = "fixture"  # fixture (simulated) | live
    voice_provider: str | None = None  # e.g. twilio | ringcentral | telnyx — set at go-live

    # email agent — inbox + workflow-sequence stats (Gmail/Workspace when live).
    email_mode: str = "fixture"  # fixture | live

    # ── Outbound outreach SEND transport — Resend on a DEDICATED sending SUBDOMAIN
    # (send.topbuilderai.com) so outreach reputation NEVER touches the root domain. Fixture by default;
    # live FAILS CLOSED without resend_api_key. Sending is gated by the action gate (ADR 0007) + the
    # deliverability/consent engine (app/outreach/compliance.py). The visible From is the subdomain;
    # Reply-To must be a REAL monitored inbox (the root has no MX).
    email_send_mode: str = "fixture"  # fixture | live (Resend)
    resend_api_key: str | None = None
    outreach_from_email: str = "outreach@send.topbuilderai.com"
    outreach_from_name: str = "Top Builder AI"
    outreach_reply_to: str | None = None  # e.g. cory.salisbury@gmail.com (root has no MX yet)
    outreach_physical_address: str = ""  # CAN-SPAM: postal address required in every email footer
    outreach_unsubscribe_base_url: str = "https://topbuilderai.com/u"  # one-click unsubscribe link base
    # New-subdomain warm-up: cap daily volume by the subdomain's age (cold-blasting a fresh domain is the
    # #1 way to get spam-filtered). cap = start * growth^age_days, clamped at outreach_daily_cap.
    outreach_warmup_start: int = 20
    outreach_warmup_growth: int = 2
    outreach_daily_cap: int = 2000  # ceiling once warmed
    # Countries that REQUIRE prior consent for commercial email (CASL/Canada, GDPR/EU, UK + EEA). The
    # engine HOLDS cold (non-consented) contacts here, never auto-sends; US cold B2B is permitted under
    # CAN-SPAM (still needs unsubscribe + address); unknown jurisdiction is HELD (fail-safe).
    outreach_consent_required_countries: str = (
        "CA,GB,IE,DE,FR,ES,IT,NL,BE,LU,AT,PT,SE,DK,FI,NO,IS,LI,CH,"
        "PL,CZ,SK,HU,RO,BG,GR,HR,SI,EE,LV,LT,CY,MT"
    )
    # HARD country block — never email these, even WITH consent (overrides the consent gate). Cory's
    # directive 2026-06-24: do not send to Canada. Comma-separated ISO-2.
    outreach_blocked_countries: str = "CA"

    # ── Operator reporting (Cory's notifications): new signups, chatbot/assistant requests, and the
    # user-submitted bug / feature / question reports get pushed to Slack AND email. ALL knobs are
    # optional and FAIL CLOSED when unset — no webhook + no operator emails = the platform runs
    # normally and notifications are silently skipped (logged). Email reuses the email_send transport
    # (fixture layer works offline); Slack posts a webhook. Per-event toggles let a noisy kind be muted.
    slack_webhook_url: str | None = None
    operator_notify_emails: str = ""  # comma-separated recipient list (Cory + any ops address)
    notify_on_signup: bool = True
    notify_on_chatbot: bool = True
    notify_on_bug: bool = True
    notify_on_feature: bool = True
    notify_on_question: bool = True

    @property
    def operator_notify_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.operator_notify_emails.split(",") if e.strip()}

    # ── Tripwire order capture (Stripe Payment Links). ALL knobs optional and FAIL CLOSED:
    # no stripe_webhook_secret -> POST /v1/tripwires/stripe/webhook is dark (404); no
    # crm_sync_db_url -> buyers are recorded + alerted but never synced to the Salisbury CRM.
    stripe_webhook_secret: str | None = None  # whsec_... from the Stripe webhook endpoint
    crm_sync_db_url: str | None = None  # Salisbury CRM Postgres DSN (asyncpg; pooler-safe)
    tripwire_slack_enabled: bool = True  # mute the per-sale Slack ping without touching the webhook

    # seo/geo marketing agent — competitor/keyword/page intel (search + community APIs when live).
    seo_mode: str = "fixture"  # fixture | live

    # action execution (ADR 0007) — the human-approved write path. OFF by default: the platform is
    # advisory-only until a customer opts in. `actions_allowed_kinds` is the per-kind allowlist.
    actions_enabled: bool = False
    actions_allowed_kinds: str = (  # comma-separated
        "book_appointment,file_document,request_signature,create_estimate,"
        "send_email_reply,delete_emails,rewrite_workflow,publish_blog_post,post_comment,"
        "payroll_adjustment,create_ap_draft,register_warranty,"
        "send_dunning_email,send_dunning_sms,place_dunning_call,"
        "update_pricebook_item,send_outreach_email,"
        "ads.create_campaign,ads.update_budget,ads.activate_campaign,"
        "ads.pause_campaign,ads.sync_conversion"
    )

    @property
    def actions_allowed_kind_set(self) -> set[str]:
        return {k.strip() for k in self.actions_allowed_kinds.split(",") if k.strip()}

    @property
    def outreach_consent_required_country_set(self) -> set[str]:
        return {
            c.strip().upper()
            for c in self.outreach_consent_required_countries.split(",")
            if c.strip()
        }

    @property
    def outreach_blocked_country_set(self) -> set[str]:
        return {c.strip().upper() for c in self.outreach_blocked_countries.split(",") if c.strip()}

    @property
    def is_dev(self) -> bool:
        return self.env.lower() == "dev"

    @property
    def platform_operator_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.platform_operator_emails.split(",") if e.strip()}

    @property
    def cors_origins(self) -> list[str]:
        if self.allowed_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        if self.trusted_hosts.strip() == "*":
            return ["*"]
        return [h.strip() for h in self.trusted_hosts.split(",") if h.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
