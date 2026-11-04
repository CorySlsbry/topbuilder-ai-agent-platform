"""Pure tests for the Collections service helpers + dunning executors (no DB).

Covers: the server-side ``proposed_dunning_params`` gate (refuses current/reconciled + no-channel,
maps the compliance-gated channel to the right action kind) and the three dunning executors run
through the provider-agnostic simulated VoiceClient (offline, deterministic) + their undos.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.actions.executors import ActionError
from app.agents.collections import executors as ex
from app.agents.collections import service
from app.agents.collections.analytics import analyze
from app.agents.collections.models import (
    CollectionsData,
    ContactPreference,
    OpenInvoice,
    PromiseToPay,
)
from app.agents.collections.schemas import build_result
from app.config import get_settings

AS_OF = date(2026, 6, 15)


def _due_days_ago(n: int) -> date:
    return AS_OF - timedelta(days=n)


def _result():
    invoices = [
        OpenInvoice("I1", "c-email", "Email Co", 5_000_000,
                    issued=_due_days_ago(35), due=_due_days_ago(5)),  # 1-30 -> step1 email
        OpenInvoice("I2", "c-sms", "SMS Co", 8_000_000,
                    issued=_due_days_ago(80), due=_due_days_ago(47)),  # 31-60 -> step2 sms
        OpenInvoice("I3", "c-call", "Call Co", 9_000_000,
                    issued=_due_days_ago(160), due=_due_days_ago(130)),  # 121+ -> step5 call
        OpenInvoice("I4", "c-current", "Current Co", 2_000_000,
                    issued=_due_days_ago(20), due=_due_days_ago(-10)),  # not yet due -> reconciled
        OpenInvoice("I5", "c-promise", "Promise Co", 3_000_000,
                    issued=_due_days_ago(60), due=_due_days_ago(30)),  # overdue but promise covers
        OpenInvoice("I6", "c-nochan", "NoChannel Co", 4_000_000,
                    issued=_due_days_ago(80), due=_due_days_ago(50)),  # step2 but no reachable channel
    ]
    promises = [
        PromiseToPay("c-promise", promised_date=date(2026, 6, 25), promised_amount_cents=3_000_000,
                     recorded_at=datetime(2026, 6, 10, tzinfo=timezone.utc)),
    ]
    contacts = [
        ContactPreference("c-email", email="person1@example.com"),
        ContactPreference("c-sms", email="person2@example.com", phone="+1555", sms_opt_in=True),
        ContactPreference("c-call", email="person3@example.com", phone="+1555", sms_opt_in=True),  # call allowed
        ContactPreference("c-current", email="person4@example.com"),
        ContactPreference("c-promise", email="person5@example.com"),
        ContactPreference("c-nochan", email=None, phone="+1555", do_not_call=True),  # sms no consent, no email
    ]
    data = CollectionsData(as_of=AS_OF, invoices=invoices, promises=promises, contacts=contacts)
    return build_result(analyze(data), narrative="x", analysis_timestamp=datetime.now(timezone.utc))


class TestProposedDunningParams:
    @pytest.mark.parametrize(
        "customer_id, expected_kind",
        [
            ("c-email", "send_dunning_email"),
            ("c-sms", "send_dunning_sms"),
            ("c-call", "place_dunning_call"),
        ],
    )
    def test_channel_maps_to_action_kind(self, customer_id: str, expected_kind: str) -> None:
        kind, params = service.proposed_dunning_params(_result(), customer_id)
        assert kind == expected_kind
        assert params["customer_id"] == customer_id
        assert params["run_id"] is None or isinstance(params["run_id"], str)

    def test_email_params_carry_the_draft(self) -> None:
        _, params = service.proposed_dunning_params(_result(), "c-email")
        assert params["email_body"] and "$50,000.00" in params["email_body"]

    def test_refuses_reconciled_customer(self) -> None:
        with pytest.raises(ValueError, match="current/reconciled"):
            service.proposed_dunning_params(_result(), "c-current")

    def test_refuses_promise_parked_customer(self) -> None:
        # parked on a covering promise -> step 0 / no channel -> refused (not "current", but no channel)
        with pytest.raises(ValueError):
            service.proposed_dunning_params(_result(), "c-promise")

    def test_refuses_no_reachable_channel(self) -> None:
        with pytest.raises(ValueError, match="no compliant outreach channel"):
            service.proposed_dunning_params(_result(), "c-nochan")

    def test_refuses_unknown_customer(self) -> None:
        with pytest.raises(ValueError, match="not in this collections run"):
            service.proposed_dunning_params(_result(), "nope")


class TestDunningExecutors:
    async def test_email_executor_fixture_confirmation(self) -> None:
        s = get_settings()
        out = await ex.send_dunning_email(
            {"customer_id": "c1", "email_body": "pay up", "email_subject": "x", "dunning_step": 1}, s
        )
        assert out["status"] == "sent" and out["external_ref"] == "dun-email-c1"

    async def test_email_executor_requires_body(self) -> None:
        with pytest.raises(ActionError, match="email_body"):
            await ex.send_dunning_email({"customer_id": "c1"}, get_settings())

    async def test_sms_executor_uses_simulated_voice_client(self) -> None:
        out = await ex.send_dunning_sms(
            {"customer_id": "c1", "sms_body": "pay up", "dunning_step": 2, "phone": "+1555"},
            get_settings(),
        )
        assert out["status"] == "sent"
        assert out["mode"] == "simulated" and out["provider"] == "simulated"

    async def test_call_executor_uses_simulated_voice_client(self) -> None:
        out = await ex.place_dunning_call(
            {"customer_id": "c1", "call_script": "hi", "dunning_step": 5, "phone": "+1555"},
            get_settings(),
        )
        assert out["status"] == "placed" and out["mode"] == "simulated"

    async def test_call_executor_requires_script(self) -> None:
        with pytest.raises(ActionError, match="call_script"):
            await ex.place_dunning_call({"customer_id": "c1"}, get_settings())

    async def test_undos_are_compensations_not_unsends(self) -> None:
        s = get_settings()
        assert (await ex.undo_send_dunning_email({}, {"external_ref": "e"}, s))["status"] == "retraction_logged"
        assert (await ex.undo_send_dunning_sms({}, {"external_ref": "s"}, s))["status"] == "marked_not_sent"
        assert (await ex.undo_place_dunning_call({}, {"external_ref": "c"}, s))["status"] == "call_retraction_logged"
