"""Fixture-backed Collections client. Invoice/promise dates are day offsets from `as_of` (evergreen).

The fixture mirrors the client's real Outstanding-A/R Google Sheet (Summit Heat Pumps): real
customer names, a balance ladder across every aging bucket, one disputed account, one promise-to-pay,
and contact prefs that exercise the TCPA/do-not-call channel downgrades. Open balance sums >$400K.
"""
from __future__ import annotations

import json
import pathlib
from datetime import date, datetime, time, timedelta, timezone

from app.agents.collections.models import ContactPreference, OpenInvoice, PromiseToPay

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


def _load(name: str):
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


class FixtureCollectionsClient:
    def __init__(self, as_of: date | None = None) -> None:
        self.as_of = as_of or date.today()
        self._invoices = _load("open_invoices.json")
        self._promises = _load("promises.json")
        self._contacts = _load("contacts.json")

    async def get_open_invoices(self) -> list[OpenInvoice]:
        return [
            OpenInvoice(
                id=row["id"],
                customer_id=row["customer_id"],
                customer_name=row["customer_name"],
                balance_cents=int(row["balance_cents"]),
                issued=self.as_of + timedelta(days=int(row["issued_offset"])),
                due=self.as_of + timedelta(days=int(row["due_offset"])),
                doc_number=row.get("doc_number"),
                customer_segment=row.get("customer_segment", "residential"),
                in_dispute=bool(row.get("in_dispute", False)),
            )
            for row in self._invoices
        ]

    async def get_promises(self) -> list[PromiseToPay]:
        return [
            PromiseToPay(
                customer_id=row["customer_id"],
                promised_date=self.as_of + timedelta(days=int(row["promised_date_offset"])),
                promised_amount_cents=int(row["promised_amount_cents"]),
                recorded_at=datetime.combine(
                    self.as_of + timedelta(days=int(row["recorded_at_offset"])),
                    time(hour=12),
                    tzinfo=timezone.utc,
                ),
                note=row.get("note"),
            )
            for row in self._promises
        ]

    async def get_contacts(self) -> list[ContactPreference]:
        return [
            ContactPreference(
                customer_id=row["customer_id"],
                email=row.get("email"),
                phone=row.get("phone"),
                sms_opt_in=bool(row.get("sms_opt_in", False)),
                do_not_call=bool(row.get("do_not_call", False)),
            )
            for row in self._contacts
        ]
