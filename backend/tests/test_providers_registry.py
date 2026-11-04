"""Provider registry — pure tests for the dynamic multi-provider layer."""
from __future__ import annotations

from app.integrations.providers import registry


def test_registry_has_exactly_ten_providers():
    assert len(registry.PROVIDERS) == 10


def test_servicetitan_is_default_flagship_and_connect_ready():
    # Honesty: 'live' means VERIFIED against a real tenant (ADR 0005). Until a customer tenant has
    # verified the mappers, the flagship reports adapter_ready — never a claimed live integration.
    assert registry.DEFAULT_PROVIDER == "servicetitan"
    st = registry.get_provider("servicetitan")
    assert st is not None and st.status == "adapter_ready" and st.segment == "home_services"


def test_expected_top_ten_slugs_present():
    assert set(registry.PROVIDERS) == {
        "servicetitan", "housecall_pro", "jobber", "fieldedge", "service_fusion",
        "workiz", "jobnimbus", "acculynx", "buildertrend", "procore",
    }


def test_segments_cover_contractors_and_builders():
    segments = {p.segment for p in registry.PROVIDERS.values()}
    assert segments == {"home_services", "construction"}
    assert {p.slug for p in registry.PROVIDERS.values() if p.segment == "construction"} == {
        "buildertrend", "procore",
    }


def test_every_provider_well_formed():
    for p in registry.PROVIDERS.values():
        assert p.display and p.api_base.startswith("https://")
        assert p.domains and set(p.domains) <= set(registry.ALL_DOMAINS)
        assert "jobs" in p.domains  # every system has work/jobs at its core


def test_display_name_resolution_and_fallback():
    assert registry.display_name("housecall_pro") == "Housecall Pro"
    assert registry.display_name("procore") == "Procore"
    assert registry.display_name("not-a-system") == "ServiceTitan"
    assert registry.display_name("") == "ServiceTitan"


def test_is_valid_normalizes_case_and_whitespace():
    assert registry.is_valid(" Jobber ") and registry.is_valid("BUILDERTREND")
    assert not registry.is_valid("salesforce")


def test_as_list_shape_for_api():
    items = registry.as_list()
    assert len(items) == 10
    sample = items[0]
    assert set(sample) == {
        "slug", "display", "segment", "domains", "status", "notes", "auth_kind", "connect",
    }


def test_every_provider_has_connection_readiness():
    """Each platform ships with its go-live setup encoded: how it authenticates and what the
    customer hands over (docs/PROVIDER_ONBOARDING.md is the long-form companion)."""
    for p in registry.PROVIDERS.values():
        assert p.auth_kind in {"oauth2", "api_key", "partner"}, p.slug
        assert p.connect, f"{p.slug} is missing its connect instructions"
    # Partner-gated APIs say so explicitly — sales must set expectations honestly.
    assert registry.get_provider("fieldedge").auth_kind == "partner"
    assert registry.get_provider("buildertrend").auth_kind == "partner"
    # The flagship live integration is OAuth2 via the customer's own account.
    assert registry.get_provider("servicetitan").auth_kind == "oauth2"
