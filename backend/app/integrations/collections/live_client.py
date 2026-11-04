"""Fail-closed live Collections client (ADR 0005): raises rather than fabricate A/R figures.

Wiring point (per ``docs/QBO_DATA_MAP.md`` §2/§3.1 — direct first-party API, NO Zapier):
  * ``get_open_invoices`` -> QBO ``AgedReceivableDetail`` (every open invoice + days overdue) joined
    with ``Invoice WHERE Balance > '0'`` (doc number, due date) and ``Customer`` (names/segments);
    or ServiceTitan ``accounting/v2`` invoice AR aging as a cross-check. Money read as integer cents.
  * ``get_promises`` -> our OWN store (the sheet's dated-notes / promise-to-pay live in our DB, not in
    QBO) — wire to the collections promise repository once persisted server-side.
  * ``get_contacts`` -> QBO/ServiceTitan customer contact + our consent ledger (sms_opt_in/do_not_call).

Until each is mapped + verified against a live company, every method raises ``NotImplementedError`` so a
partial connection surfaces as a clear error, never a wrong A/R figure (ADR 0003).
"""
from __future__ import annotations

from app.agents.collections.models import ContactPreference, OpenInvoice, PromiseToPay
from app.config import Settings


class LiveCollectionsClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def get_open_invoices(self) -> list[OpenInvoice]:
        raise NotImplementedError(
            "live A/R read is not yet wired; map QBO AgedReceivableDetail + Invoice(Balance>0) + "
            "Customer to OpenInvoice (cents) and verify against a real company (ADR 0005)."
        )

    async def get_promises(self) -> list[PromiseToPay]:
        raise NotImplementedError(
            "live promise-to-pay read is not yet wired; source from our collections promise store."
        )

    async def get_contacts(self) -> list[ContactPreference]:
        raise NotImplementedError(
            "live contact/consent read is not yet wired; map customer contact + the consent ledger."
        )
