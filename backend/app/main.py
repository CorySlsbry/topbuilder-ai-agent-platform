"""FastAPI application factory for Top Builder AI."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import (
    routes_actions,
    routes_admin,
    routes_ads,
    routes_ads_oauth,
    routes_assistant,
    routes_auth,
    routes_booking,
    routes_capacity,
    routes_collections,
    routes_comms,
    routes_connections,
    routes_crm,
    routes_data_rights,
    routes_documents,
    routes_email,
    routes_feedback,
    routes_fieldops,
    routes_financial,
    routes_google_oauth,
    routes_health,
    routes_integrations,
    routes_inventory,
    routes_knowledge,
    routes_learning,
    routes_org,
    routes_payroll,
    routes_policies,
    routes_pricebook,
    routes_providers,
    routes_qbo_oauth,
    routes_routing,
    routes_seo,
    routes_support,
    routes_sync,
    routes_tasks,
    routes_tripwires,
    routes_voice,
    routes_webhooks,
    routes_workforce,
)
from app.config import get_settings
from app.errors import register_error_handlers
from app.logging_config import configure_logging, get_logger
from app.middleware import RateLimitMiddleware, RequestContextMiddleware
from app.ratelimit import RateLimiter

DESCRIPTION = """\
Enterprise multi-agent decision platform for ServiceTitan contractors.

This service exposes the **Workforce Optimization** agent: it turns scheduling, timesheet, and demand
data into board-grade understaffing and overtime recommendations — every figure deterministic and
audited, every tenant isolated by Postgres Row-Level Security.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    log = get_logger("app")
    log.info(
        "startup",
        env=settings.env,
        auth_mode=settings.auth_mode,
        servicetitan_mode=settings.servicetitan_mode,
    )
    yield
    try:  # graceful shutdown — release DB connections
        from app.db import get_engine

        await get_engine().dispose()
    except Exception:  # nothing was opened; ignore
        pass


def _assert_production_config(settings) -> None:
    """Fail FAST at boot if a production service is misconfigured in a way that would weaken auth or
    open the edge — a forgotten go-live flip must crash the boot, not run insecurely (defense against the
    'flipped ENV=prod but forgot AUTH_MODE / CORS / the secret' footgun the audit flagged)."""
    if settings.is_dev:
        return
    problems: list[str] = []
    if settings.auth_mode.lower() not in {"jwks", "supabase"}:
        problems.append(f"AUTH_MODE='{settings.auth_mode}' (must be 'jwks' or 'supabase' in prod)")
    if not settings.jwt_secret or settings.jwt_secret == "change-me" or len(settings.jwt_secret) < 32:
        problems.append("JWT_SECRET is unset/default/too short (need a rotated 32+ byte secret)")

    def _wild(v) -> bool:
        return v == "*" or (isinstance(v, (list, tuple)) and "*" in v)

    if _wild(getattr(settings, "allowed_origins", None)):
        problems.append("ALLOWED_ORIGINS='*' (lock to the dashboard origin in prod)")
    if _wild(getattr(settings, "trusted_hosts", None)):
        problems.append("TRUSTED_HOSTS='*' (lock to the API host in prod)")
    if not settings.platform_operator_email_set:
        problems.append("PLATFORM_OPERATOR_EMAILS is empty (no platform operator allowlisted)")
    if not settings.hsts_enabled:
        problems.append("HSTS_ENABLED=false (enable behind HTTPS in prod)")
    if settings.actions_enabled:
        # The master write switch is ON: every live-mode provider must actually hold credentials,
        # or approved actions would only die at the fail-closed executor after a human approved them.
        if settings.email_send_mode.lower() == "live" and not settings.resend_api_key:
            problems.append("ACTIONS_ENABLED with EMAIL_SEND_MODE=live but no RESEND_API_KEY")
        if settings.servicetitan_mode.lower() == "live" and not settings.servicetitan_client_secret:
            problems.append("ACTIONS_ENABLED with SERVICETITAN_MODE=live but no ServiceTitan credentials")
    for field, label in (
        ("webhook_signing_secret", "WEBHOOK_SIGNING_SECRET"),
        ("cron_secret", "CRON_SECRET"),
        ("credential_encryption_key", "CREDENTIAL_ENCRYPTION_KEY"),
    ):
        if not getattr(settings, field, None):
            get_logger("app.boot").warning(
                "%s is unset — its feature stays dormant (fail-closed); set it before go-live", label
            )
    # DB TLS: verify is strongly recommended, but the Supabase pooler signs with a project CA that
    # does not chain to a public root, and CA-pinning (DB_SSL_CA) is not built yet — so requiring
    # verify would brick the boot with no config escape. Warn loudly instead of hard-failing.
    if not settings.db_ssl_verify:
        get_logger("app.boot").warning(
            "DB_SSL_VERIFY=false — DB traffic is encrypted but the pooler cert is unverified; "
            "pin the Supabase CA and enable verification before real customer data"
        )
    if problems:
        raise RuntimeError(
            "Refusing to boot: production (ENV!=dev) is misconfigured — " + "; ".join(problems)
        )


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    _assert_production_config(settings)

    # The interactive docs + raw schema publish the entire API surface. Keep them on for the dev
    # demo; suppress them at ENV=prod so they aren't an anonymous reconnaissance aid.
    _docs = {} if settings.is_dev else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(
        title="Top Builder AI API",
        version="0.1.0",
        description=DESCRIPTION,
        lifespan=lifespan,
        **_docs,
        openapi_tags=[
            {"name": "health", "description": "Liveness / readiness."},
            {"name": "auth", "description": "Dev token issuance (ENV=dev)."},
            {"name": "workforce", "description": "Workforce Optimization agent."},
            {"name": "financial", "description": "Financial Forecasting agent."},
            {"name": "inventory", "description": "Inventory & Supply Chain agent."},
            {"name": "booking", "description": "24/7 Booking agent — qualify, slot, and value inbound intakes."},
            {"name": "routing", "description": "Routing / Dispatch agent — drive-time-optimized assignment plan."},
            {"name": "documents", "description": "Documents agent — classify, route to customer/department/ServiceTitan folder, flag e-sign."},
            {"name": "pricebook", "description": "Pricebook agent — re-price catalog items from vendor cost updates under the sold-hour model."},
            {"name": "fieldops", "description": "Field-ops mobile surface — tech jobs, pricebook, and the custom-quote builder."},
            {"name": "feedback", "description": "Feedback / training loop — humans rate, edit, and correct agent output to train it."},
            {"name": "actions", "description": "Human-approved action execution — propose → approve → execute (ADR 0007)."},
            {"name": "operations", "description": "Front-desk operating layer — communications inbox + task worklist."},
            {"name": "connections", "description": "Per-tenant integration credential vault."},
            {"name": "webhooks", "description": "Inbound ServiceTitan webhooks + event queue."},
            {"name": "sync", "description": "Event detection -> auto-act (ADR 0010): change-feed poll + drain crons, app-owned emit, dead-letters."},
            {"name": "knowledge", "description": "RAG 'Learn' module — upload + semantic search."},
            {"name": "crm", "description": "Operator-only Ads-CRM — leads / contacts / activities pipeline (ADR 0009)."},
            {"name": "ads", "description": "Operator-only ad platforms — accounts, templates, gated campaign builds + metrics (ADR 0009)."},
            {"name": "support", "description": "Operator reporting — capture signups / assistant requests / bug / feature / question and notify Slack + email."},
            {"name": "tripwires", "description": "Tripwire order capture — Stripe Payment Link webhook (signature-verified, idempotent), Slack sale alerts, best-effort Salisbury-CRM buyer sync."},
        ],
    )

    register_error_handlers(app)

    # Middleware: the LAST added is OUTERMOST. Desired order (outer -> inner):
    # TrustedHost -> CORS -> RequestContext(logging/headers) -> RateLimit -> routes.
    app.add_middleware(
        RateLimitMiddleware,
        limiter=RateLimiter(settings.rate_limit_per_minute, settings.rate_limit_burst),
    )
    app.add_middleware(RequestContextMiddleware, hsts_enabled=settings.hsts_enabled)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,  # bearer tokens, not cookies
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)

    app.include_router(routes_health.router)
    app.include_router(routes_auth.router)
    app.include_router(routes_workforce.router)
    app.include_router(routes_payroll.router)  # payroll advisory run + gated payroll_adjustment
    app.include_router(routes_capacity.router)  # rolling-capacity advisory (Workforce); agent="capacity"
    app.include_router(routes_financial.router)
    app.include_router(routes_inventory.router)
    app.include_router(routes_booking.router)
    app.include_router(routes_collections.router)  # A/R Collections agent (dunning + promise-to-pay)
    app.include_router(routes_pricebook.router)  # Pricebook agent (cost-driven re-pricing under sold-hour model)
    app.include_router(routes_routing.router)
    app.include_router(routes_documents.router)
    app.include_router(routes_email.router)  # operator-only (super-admin layer)
    app.include_router(routes_fieldops.router)
    app.include_router(routes_feedback.router)
    app.include_router(routes_actions.router)
    app.include_router(routes_policies.router)
    app.include_router(routes_providers.router)  # dynamic field-system layer (top-10 registry)
    app.include_router(routes_comms.router)
    app.include_router(routes_tasks.router)
    app.include_router(routes_connections.router)
    app.include_router(routes_integrations.router)  # per-customer OAuth onboarding (Procore)
    app.include_router(routes_google_oauth.router)  # per-customer OAuth onboarding (Google Drive/Sheets)
    app.include_router(routes_qbo_oauth.router)  # per-customer OAuth onboarding (QuickBooks Online / Intuit)
    app.include_router(routes_ads_oauth.router)  # operator-only ad-platform OAuth (Meta / Google Ads, PKCE)
    app.include_router(routes_data_rights.router)  # retention policy + right-to-erasure purge (operator)
    app.include_router(routes_webhooks.router)
    app.include_router(routes_sync.router)  # event detection -> auto-act crons + emit (ADR 0010)
    app.include_router(routes_knowledge.router)
    app.include_router(routes_learning.router)
    app.include_router(routes_org.router)  # Organization Brain (seeded org + caller access)
    app.include_router(routes_seo.router)  # operator-only (super-admin layer)
    app.include_router(routes_admin.router)  # operator-only (memberships / invites)
    app.include_router(routes_assistant.router)  # in-app assistant (Sonnet tool loop, capped)
    app.include_router(routes_voice.router)  # booking-agent phone voice (registry + tenant pick)
    app.include_router(routes_crm.router)  # operator-only Ads-CRM leads pipeline (ADR 0009)
    app.include_router(routes_ads.router)  # operator-only ad accounts / campaigns / metrics (ADR 0009)
    app.include_router(routes_support.router)  # operator reporting: signups/chatbot/bug/feature/question
    app.include_router(routes_tripwires.router)  # tripwire orders: Stripe webhook + operator list

    @app.get("/", tags=["health"])
    async def root() -> dict:
        return {"name": "Top Builder AI API", "version": "0.1.0", "docs": "/docs"}

    return app


app = create_app()
