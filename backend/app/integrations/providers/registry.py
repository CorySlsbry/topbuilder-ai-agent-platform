"""The field-system provider registry — the top 10 platforms contractors and builders run on.

The platform is provider-agnostic: agents consume CANONICAL domain models (jobs, intakes, parts,
documents), and each provider maps onto them through an adapter. Fixture adapters exercise the whole
pipeline deterministically today; live adapters are fail-closed skeletons wired per customer at
go-live (ADR 0005), exactly as ServiceTitan's was. Narration adapts to the tenant's system by name.

Selection is per-tenant (`tenant_settings.fsm_provider`, migration 0014) with ServiceTitan as the
default. Research basis (2026): ServiceTitan/Housecall Pro/Jobber lead home-services FSM; Procore
(~18% share) and Buildertrend lead contractor-facing construction management.
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_PROVIDER = "servicetitan"

# Data domains an adapter can serve (agents consuming them in parentheses):
# jobs (workforce/routing) · intake (booking) · inventory (inventory) · documents (documents)
# · accounting (financial — note QuickBooks pairs with any of these as the ledger).
ALL_DOMAINS = ("jobs", "intake", "inventory", "documents", "accounting")


@dataclass(frozen=True)
class Provider:
    slug: str
    display: str
    segment: str  # 'home_services' | 'construction'
    api_base: str
    domains: tuple[str, ...] = field(default=ALL_DOMAINS)
    status: str = "adapter_ready"  # 'live' = verified against a real tenant; 'adapter_ready' = fixture + fail-closed live skeleton
    notes: str = ""
    # Connection readiness — what a customer hands over at go-live (docs/PROVIDER_ONBOARDING.md).
    # `connect` is CUSTOMER-FACING UI copy (second person, no dev jargon); the dashboard renders it
    # under the field-system selector. Details from public developer docs; re-verify at onboarding.
    auth_kind: str = "api_key"  # 'oauth2' | 'api_key' | 'partner'
    connect: str = ""  # one line: how the customer's account connects


PROVIDERS: dict[str, Provider] = {
    p.slug: p
    for p in (
        Provider(
            "servicetitan", "ServiceTitan", "home_services", "https://api.servicetitan.io",
            status="adapter_ready",  # honest until verified against a real tenant (ADR 0005)
            notes="Flagship integration — deepest adapter; the head-to-head agents target its AI.",
            auth_kind="oauth2",
            connect="connects when you authorize the app from your ServiceTitan account.",
        ),
        Provider("housecall_pro", "Housecall Pro", "home_services", "https://api.housecallpro.com",
                 auth_kind="api_key",
                 connect="connects with an API key from your Housecall Pro account (available on supported plans)."),
        Provider("jobber", "Jobber", "home_services", "https://api.getjobber.com/api/graphql",
                 notes="GraphQL API.",
                 auth_kind="oauth2",
                 connect="connects when you authorize the app from your Jobber account."),
        Provider("fieldedge", "FieldEdge", "home_services", "https://api.fieldedge.com",
                 notes="HVAC-focused (Xplor).",
                 auth_kind="partner",
                 connect="live hookup goes through the FieldEdge partner program — we handle the application."),
        Provider("service_fusion", "Service Fusion", "home_services", "https://api.servicefusion.com",
                 auth_kind="oauth2",
                 connect="connects when you authorize API access from your Service Fusion account."),
        Provider("workiz", "Workiz", "home_services", "https://api.workiz.com",
                 auth_kind="api_key",
                 connect="connects with an API token from your Workiz account settings."),
        Provider("jobnimbus", "JobNimbus", "home_services", "https://app.jobnimbus.com/api1",
                 notes="Roofing & exteriors CRM/FSM.",
                 auth_kind="api_key",
                 connect="connects with an API key from your JobNimbus settings."),
        Provider("acculynx", "AccuLynx", "home_services", "https://api.acculynx.com",
                 notes="Roofing restoration; insurance/supplement workflows.",
                 auth_kind="api_key",
                 connect="connects with an API key from your AccuLynx account."),
        Provider("buildertrend", "Buildertrend", "construction", "https://api.buildertrend.com",
                 domains=("jobs", "documents", "accounting"),
                 notes="Residential builders & remodelers; partner API.",
                 auth_kind="partner",
                 connect="live hookup goes through Buildertrend's partner program — we handle the application."),
        Provider("procore", "Procore", "construction", "https://api.procore.com",
                 domains=("jobs", "documents", "accounting"),
                 notes="Commercial GCs; RFIs/dailies/budgets map onto documents + jobs + accounting.",
                 auth_kind="oauth2",
                 connect="connects when you install the app from the Procore marketplace."),
    )
}


def get_provider(slug: str) -> Provider | None:
    return PROVIDERS.get((slug or "").strip().lower())


def display_name(slug: str) -> str:
    p = get_provider(slug)
    return p.display if p else PROVIDERS[DEFAULT_PROVIDER].display


def is_valid(slug: str) -> bool:
    return get_provider(slug) is not None


def as_list() -> list[dict]:
    return [
        {
            "slug": p.slug,
            "display": p.display,
            "segment": p.segment,
            "domains": list(p.domains),
            "status": p.status,
            "notes": p.notes,
            "auth_kind": p.auth_kind,
            "connect": p.connect,
        }
        for p in PROVIDERS.values()
    ]
