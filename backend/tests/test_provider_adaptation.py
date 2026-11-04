"""Pure tests for the dynamic-provider narration + metadata layer (no DB, no network).

The tenant's field-service system (`tenant_settings.fsm_provider`) must (a) be reported on the run
result as `source_system` and (b) steer the NARRATION wording — while the default (`ServiceTitan`)
path stays byte-identical to the pre-provider behavior, and the deterministic figures are never
touched (ADR 0003).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from app.agents.booking.analytics import analyze as analyze_booking
from app.agents.booking.data import assemble_booking_data
from app.agents.booking.reasoning import _template_narrative as booking_template
from app.agents.booking.reasoning import explain as booking_explain
from app.agents.booking.schemas import BookingRunResult
from app.agents.booking.schemas import build_result as build_booking_result
from app.agents.documents.analytics import analyze as analyze_documents
from app.agents.documents.models import Document, DocumentsData, KnownCustomer
from app.agents.documents.reasoning import explain as documents_explain
from app.agents.financial.analytics import analyze as analyze_financial
from app.agents.financial.data import assemble_financial_data
from app.agents.financial.reasoning import _template_narrative as financial_template
from app.agents.financial.reasoning import explain as financial_explain
from app.agents.financial.schemas import FinancialRunResult
from app.agents.financial.schemas import build_result as build_financial_result
from app.config import Settings
from app.integrations.accounting.fixture_client import FixtureAccountingClient
from app.integrations.booking_intake.fixture_client import FixtureBookingIntakeClient

CUSTOM_PROVIDER = "Housecall Pro"
DEFAULT_PROVIDER = "ServiceTitan"
FINANCIAL_AS_OF = date(2026, 6, 1)
BOOKING_AS_OF = datetime(2026, 6, 6, 19, 0)  # the after-hours fixture batch
# Forces every explain() down the deterministic TEMPLATE path — no API key is ever consulted.
TEMPLATE_SETTINGS = Settings(disable_llm=True)


async def _financial_analysis():
    client = FixtureAccountingClient(as_of=FINANCIAL_AS_OF)
    return analyze_financial(await assemble_financial_data(client, as_of=FINANCIAL_AS_OF))


async def _booking_analysis():
    client = FixtureBookingIntakeClient(as_of=BOOKING_AS_OF)
    return analyze_booking(await assemble_booking_data(client, as_of=BOOKING_AS_OF))


def _documents_analysis():
    # One auto-filed invoice — enough to put "ServiceTitan folder" in the stock template wording,
    # which exercises the rename (replace) branch rather than the appended source-line branch.
    data = DocumentsData(
        as_of=date(2026, 6, 9),
        documents=[
            Document(
                id="DOC1",
                filename="DOC1.pdf",
                mime_type="application/pdf",
                declared_type="invoice",
                customer_hint="Whitfield Residence",
                amount_cents=48_000,
            )
        ],
        customers=[KnownCustomer("CUST-1", "Whitfield Residence")],
    )
    return analyze_documents(data)


class TestNarrationAdaptsToTenantProvider:
    async def test_financial_template_names_the_custom_provider(self) -> None:
        narration = await financial_explain(
            await _financial_analysis(), TEMPLATE_SETTINGS, provider=CUSTOM_PROVIDER
        )
        assert CUSTOM_PROVIDER in narration
        assert DEFAULT_PROVIDER not in narration

    async def test_financial_default_is_byte_identical_to_the_stock_template(self) -> None:
        analysis = await _financial_analysis()
        narration = await financial_explain(analysis, TEMPLATE_SETTINGS)
        assert narration == financial_template(analysis)
        assert CUSTOM_PROVIDER not in narration

    async def test_booking_template_names_the_custom_provider(self) -> None:
        narration = await booking_explain(
            await _booking_analysis(), TEMPLATE_SETTINGS, provider=CUSTOM_PROVIDER
        )
        assert CUSTOM_PROVIDER in narration
        assert DEFAULT_PROVIDER not in narration

    async def test_booking_default_is_byte_identical_to_the_stock_template(self) -> None:
        analysis = await _booking_analysis()
        narration = await booking_explain(analysis, TEMPLATE_SETTINGS)
        assert narration == booking_template(analysis)
        assert CUSTOM_PROVIDER not in narration

    async def test_documents_template_renames_the_hardcoded_servicetitan_folder(self) -> None:
        # The documents template literally says "ServiceTitan folder" — the rename branch must
        # swap it for the tenant's system without appending a redundant source line.
        narration = await documents_explain(
            _documents_analysis(), TEMPLATE_SETTINGS, provider=CUSTOM_PROVIDER
        )
        assert f"{CUSTOM_PROVIDER} folder" in narration
        assert DEFAULT_PROVIDER not in narration
        assert "Field-service system of record" not in narration

    async def test_provider_adaptation_never_touches_a_figure(self) -> None:
        # ADR 0003: identical analysis -> identical numbers in the narration, whatever the provider.
        analysis = await _booking_analysis()
        stock = await booking_explain(analysis, TEMPLATE_SETTINGS)
        adapted = await booking_explain(analysis, TEMPLATE_SETTINGS, provider=CUSTOM_PROVIDER)
        assert "2,895" in stock and "2,895" in adapted  # the after-hours oracle dollars, verbatim
        assert adapted == stock + f"\n\nField-service system of record: {CUSTOM_PROVIDER}."


class TestSourceSystemField:
    async def test_defaults_to_servicetitan_on_built_results(self) -> None:
        financial = build_financial_result(
            await _financial_analysis(),
            narrative="n/a",
            analysis_timestamp=datetime(2026, 6, 1, 6, 0, tzinfo=timezone.utc),
        )
        booking = build_booking_result(
            await _booking_analysis(),
            narrative="n/a",
            analysis_timestamp=datetime(2026, 6, 6, 19, 1, tzinfo=timezone.utc),
        )
        assert (financial.source_system, booking.source_system) == (
            DEFAULT_PROVIDER,
            DEFAULT_PROVIDER,
        )

    async def test_custom_value_round_trips_through_dump_and_validate(self) -> None:
        financial = build_financial_result(
            await _financial_analysis(),
            narrative="n/a",
            analysis_timestamp=datetime(2026, 6, 1, 6, 0, tzinfo=timezone.utc),
            run_id=uuid.uuid4(),
            source_system=CUSTOM_PROVIDER,
        )
        assert financial.source_system == CUSTOM_PROVIDER
        revived = FinancialRunResult.model_validate(financial.model_dump(mode="json"))
        assert revived.source_system == CUSTOM_PROVIDER

        booking = build_booking_result(
            await _booking_analysis(),
            narrative="n/a",
            analysis_timestamp=datetime(2026, 6, 6, 19, 1, tzinfo=timezone.utc),
            run_id=uuid.uuid4(),
            source_system=CUSTOM_PROVIDER,
        )
        assert booking.source_system == CUSTOM_PROVIDER
        assert (
            BookingRunResult.model_validate(booking.model_dump(mode="json")).source_system
            == CUSTOM_PROVIDER
        )

    async def test_pre_provider_persisted_results_still_validate(self) -> None:
        # Rows persisted before this field existed have no `source_system` key — they must revive
        # with the flagship default (the model_validate path the run-dedup cache exercises).
        dumped = build_booking_result(
            await _booking_analysis(),
            narrative="n/a",
            analysis_timestamp=datetime(2026, 6, 6, 19, 1, tzinfo=timezone.utc),
        ).model_dump(mode="json")
        dumped.pop("source_system")
        assert BookingRunResult.model_validate(dumped).source_system == DEFAULT_PROVIDER
