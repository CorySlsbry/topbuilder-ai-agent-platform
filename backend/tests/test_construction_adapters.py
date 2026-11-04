"""Construction adapters (Buildertrend, Procore) — fail-closed contract tests.

PURE: no network, no DB. These lock the go-live safety property for the construction platforms, exactly
as `test_go_live_failclosed.py` does for ServiceTitan: a live-mode adapter that lacks credentials, or
whose endpoint mapping isn't wired yet, RAISES — it never fabricates data (ADR 0005 / the ADR-0003
figure firewall). Run with: cd backend && pytest -q -m "not integration".
"""
from __future__ import annotations

from datetime import date

import pytest

from app.config import Settings
from app.integrations.construction.buildertrend_client import LiveBuildertrendClient
from app.integrations.construction.dispatch import (
    get_construction_client,
    get_fsm_live_client,
)
from app.integrations.construction.procore_client import LiveProcoreClient
from app.integrations.providers.registry import get_provider
from app.integrations.servicetitan.live_client import LiveServiceTitanClient

# No construction credentials set -> live clients must fail closed.
NO_CREDS = Settings(buildertrend_mode="live", procore_mode="live")


class TestRequireCredentialsFailsClosed:
    def test_buildertrend_requires_credentials(self) -> None:
        with pytest.raises(RuntimeError, match="BUILDERTREND_API_KEY"):
            LiveBuildertrendClient(NO_CREDS)._require_credentials()

    def test_procore_requires_credentials(self) -> None:
        with pytest.raises(RuntimeError, match="PROCORE_CLIENT_ID"):
            LiveProcoreClient(NO_CREDS)._require_credentials()

    def test_procore_names_every_missing_credential(self) -> None:
        with pytest.raises(RuntimeError) as exc:
            LiveProcoreClient(NO_CREDS)._require_credentials()
        message = str(exc.value)
        for name in (
            "PROCORE_CLIENT_ID",
            "PROCORE_CLIENT_SECRET",
            "PROCORE_REFRESH_TOKEN",
            "PROCORE_COMPANY_ID",
        ):
            assert name in message


class TestDispatcherRouting:
    def test_get_construction_client_buildertrend(self) -> None:
        client = get_construction_client("buildertrend", NO_CREDS)
        assert isinstance(client, LiveBuildertrendClient)

    def test_get_construction_client_procore(self) -> None:
        client = get_construction_client("procore", NO_CREDS)
        assert isinstance(client, LiveProcoreClient)

    def test_get_construction_client_is_case_and_space_insensitive(self) -> None:
        assert isinstance(get_construction_client("  Procore ", NO_CREDS), LiveProcoreClient)

    @pytest.mark.parametrize("slug", ["servicetitan", "housecall_pro", "", "unknown"])
    def test_get_construction_client_raises_on_non_construction(self, slug: str) -> None:
        # ServiceTitan is a valid FSM but NOT a construction platform -> the construction-only
        # dispatcher must refuse it, never silently return a default.
        with pytest.raises(ValueError):
            get_construction_client(slug, NO_CREDS)

    def test_get_fsm_live_client_routes_servicetitan(self) -> None:
        assert isinstance(get_fsm_live_client("servicetitan", NO_CREDS), LiveServiceTitanClient)

    def test_get_fsm_live_client_routes_buildertrend(self) -> None:
        assert isinstance(get_fsm_live_client("buildertrend", NO_CREDS), LiveBuildertrendClient)

    def test_get_fsm_live_client_routes_procore(self) -> None:
        assert isinstance(get_fsm_live_client("procore", NO_CREDS), LiveProcoreClient)

    @pytest.mark.parametrize("slug", ["housecall_pro", "jobber", "", "nope"])
    def test_get_fsm_live_client_raises_on_unsupported(self, slug: str) -> None:
        with pytest.raises(ValueError):
            get_fsm_live_client(slug, NO_CREDS)


class TestRegistryConstructionEntries:
    @pytest.mark.parametrize("slug", ["buildertrend", "procore"])
    def test_segment_is_construction(self, slug: str) -> None:
        provider = get_provider(slug)
        assert provider is not None
        assert provider.segment == "construction"

    @pytest.mark.parametrize("slug", ["buildertrend", "procore"])
    def test_domains_are_exactly_jobs_documents_accounting(self, slug: str) -> None:
        provider = get_provider(slug)
        assert provider is not None
        assert provider.domains == ("jobs", "documents", "accounting")


class TestLiveReadsNeverFabricate:
    """The live read methods raise NotImplementedError (skeleton) — they never return faked rows.

    Each adapter has read methods that ARE wired to the paginator (none yet for construction; all here
    raise pending the per-tenant mapping). We assert every documented read surface fails closed.
    """

    async def test_buildertrend_reads_raise(self) -> None:
        c = LiveBuildertrendClient(NO_CREDS)
        for coro in (
            c.get_jobs(date.today()),
            c.get_documents(date.today()),
            c.get_customers(),
            c.get_ar_invoices(),
            c.get_ap_bills(),
        ):
            with pytest.raises(NotImplementedError):
                await coro

    async def test_procore_reads_raise(self) -> None:
        c = LiveProcoreClient(NO_CREDS)
        for coro in (
            c.get_jobs(date.today()),
            c.get_documents(date.today()),
            c.get_customers(),
            c.get_ar_invoices(),
            c.get_ap_bills(),
        ):
            with pytest.raises(NotImplementedError):
                await coro


class TestMappersAreFillInTheBlanks:
    """The mappers carry the documented source->canonical field map but raise until verified live."""

    def test_all_construction_mappers_raise_pending_live_verification(self) -> None:
        from app.integrations.construction import mappers

        for fn_name in (
            "map_buildertrend_job_to_job",
            "map_buildertrend_document_to_document",
            "map_buildertrend_customer_to_customer",
            "map_buildertrend_invoice_to_accounting",
            "map_buildertrend_po_to_accounting",
            "map_procore_project_to_job",
            "map_procore_rfi_to_document",
            "map_procore_vendor_to_customer",
            "map_procore_prime_contract_to_accounting",
            "map_procore_commitment_to_accounting",
        ):
            fn = getattr(mappers, fn_name)
            assert fn.__doc__ and "->" in fn.__doc__, f"{fn_name} must document its field map"
            with pytest.raises(NotImplementedError):
                fn({})
