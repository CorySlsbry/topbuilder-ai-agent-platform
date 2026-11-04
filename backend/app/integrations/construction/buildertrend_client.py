"""Live Buildertrend client — partner/API-key auth skeleton (ADR 0005).

The auth flow and paginator are fully implemented (and unit-testable). The per-endpoint response
mapping is intentionally left to be filled against a real tenant, because the exact field shapes and
units must be verified with live data rather than guessed — see ADR 0005. Selected via
`BUILDERTREND_MODE=live`.

Buildertrend's live API is gated behind a **partnership agreement** (registry `auth_kind="partner"`),
so the customer hands over a partner-issued API key/token; there is no public self-serve OAuth flow.
The read surface maps onto the canonical domain models the construction platforms serve:

    jobs/schedules        -> jobs domain       (DispatchJob)
    documents/selections  -> documents domain  (Document)
    invoices/POs/budgets  -> accounting domain  (ARInvoice / APBill / Job cost rollup)
"""
from __future__ import annotations

from datetime import date
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.agents.documents.models import Document, KnownCustomer
from app.agents.financial.models import APBill, ARInvoice
from app.agents.routing.models import DispatchJob
from app.config import Settings


class LiveBuildertrendClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    def _require_credentials(self) -> None:
        missing = [
            name
            for name, value in {
                "BUILDERTREND_API_KEY": self._s.buildertrend_api_key,
                "BUILDERTREND_PARTNER_TOKEN": self._s.buildertrend_partner_token,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Buildertrend live mode requires: " + ", ".join(missing)
            )

    async def _headers(self) -> dict[str, str]:
        # Partner API-key auth: the partner token authorizes the integration, the API key scopes the
        # customer's builder account. Exact header names are confirmed with the partner program.
        self._require_credentials()
        return {
            "Authorization": f"Bearer {self._s.buildertrend_partner_token or ''}",
            "X-Api-Key": self._s.buildertrend_api_key or "",
            "Accept": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=8))
    async def _get_paginated(self, path: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Follow Buildertrend's page-number pagination, returning all item rows."""
        headers = await self._headers()
        params = dict(params or {})
        params.setdefault("pageSize", 100)
        page = 1
        items: list[dict] = []
        async with httpx.AsyncClient(base_url=self._s.buildertrend_base_url, timeout=60) as client:
            while True:
                params["page"] = page
                resp = await client.get(path, params=params, headers=headers)
                resp.raise_for_status()
                body = resp.json()
                rows = body.get("items", body.get("data", []))
                items.extend(rows)
                if len(rows) < params["pageSize"] or not rows:
                    break
                page += 1
        return items

    # -- jobs domain -------------------------------------------------------------------
    # Endpoints below are the documented Buildertrend API paths. Fill the row->model mapping against a
    # real tenant (verify field names and units first).

    async def get_jobs(self, as_of: date) -> list[DispatchJob]:
        # GET /v1/jobs (+ /v1/schedules) -> DispatchJob (project the job site address to zone coords).
        raise NotImplementedError(
            "Map Buildertrend jobs/schedules -> DispatchJob "
            "(jobs/schedules domain; verify address -> zone coords + window units)."
        )

    # -- documents domain --------------------------------------------------------------

    async def get_documents(self, as_of: date) -> list[Document]:
        # GET /v1/documents (+ /v1/selections) -> Document (run OCR/extraction on the file payload).
        raise NotImplementedError(
            "Map Buildertrend documents/selections -> Document "
            "(documents/selections domain; verify amount/expiry/signed extraction)."
        )

    async def get_customers(self) -> list[KnownCustomer]:
        # GET /v1/customers (owners/contacts) -> KnownCustomer (for matching).
        raise NotImplementedError(
            "Map Buildertrend customers/owners -> KnownCustomer (documents domain match key)."
        )

    # -- accounting domain -------------------------------------------------------------

    async def get_ar_invoices(self) -> list[ARInvoice]:
        # GET /v1/invoices -> ARInvoice (customer-billed; segment from the job/owner type).
        raise NotImplementedError(
            "Map Buildertrend invoices -> ARInvoice "
            "(invoices/POs/budgets domain; verify issued/due dates + paid status)."
        )

    async def get_ap_bills(self) -> list[APBill]:
        # GET /v1/purchase-orders (+ bills) -> APBill (vendor payables from POs/budgets).
        raise NotImplementedError(
            "Map Buildertrend purchase-orders/budgets -> APBill "
            "(invoices/POs/budgets domain; verify vendor + due date + amount units)."
        )
