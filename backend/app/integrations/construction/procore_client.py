"""Live Procore client — marketplace OAuth2 skeleton (ADR 0005).

The auth flow and paginator are fully implemented (and unit-testable). The per-endpoint response
mapping is intentionally left to be filled against a real tenant, because the exact field shapes and
units must be verified with live data rather than guessed — see ADR 0005. Selected via
`PROCORE_MODE=live`.

Procore uses marketplace OAuth2: the customer installs the app and grants access, yielding a refresh
token. This client requests a short-lived access token with `grant_type=refresh_token` (refresh-aware,
fail-closed) and scopes calls to the customer's `company_id`. The read surface maps onto the canonical
domain models the construction platforms serve:

    projects                          -> jobs domain       (DispatchJob)
    RFIs/submittals/daily-logs        -> documents domain  (Document)
    budgets/prime-contracts/change-orders -> accounting domain (ARInvoice / APBill / Job cost rollup)
"""
from __future__ import annotations

import time
from datetime import date
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.agents.documents.models import Document, KnownCustomer
from app.agents.financial.models import APBill, ARInvoice
from app.agents.routing.models import DispatchJob
from app.config import Settings


class LiveProcoreClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._token: str | None = None
        self._token_expiry_monotonic: float = 0.0

    def _require_credentials(self) -> None:
        missing = [
            name
            for name, value in {
                "PROCORE_CLIENT_ID": self._s.procore_client_id,
                "PROCORE_CLIENT_SECRET": self._s.procore_client_secret,
                "PROCORE_REFRESH_TOKEN": self._s.procore_refresh_token,
                "PROCORE_COMPANY_ID": self._s.procore_company_id,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Procore live mode requires: " + ", ".join(missing)
            )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=8))
    async def _access_token(self) -> str:
        self._require_credentials()
        now = time.monotonic()
        if self._token is not None and now < self._token_expiry_monotonic - 60:
            return self._token
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self._s.procore_auth_url,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self._s.procore_client_id,
                    "client_secret": self._s.procore_client_secret,
                    "refresh_token": self._s.procore_refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            token = resp.json()
        self._token = token["access_token"]
        # Procore rotates the refresh token on each exchange; persist token["refresh_token"] to the
        # credential vault at go-live so the next exchange uses the current one.
        self._token_expiry_monotonic = now + float(token.get("expires_in", 7200))
        return self._token

    async def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {await self._access_token()}",
            "Procore-Company-Id": self._s.procore_company_id or "",
            "Accept": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=8))
    async def _get_paginated(self, path: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Follow Procore's per_page/page pagination, returning all rows."""
        headers = await self._headers()
        params = dict(params or {})
        params.setdefault("per_page", 100)
        page = 1
        items: list[dict] = []
        async with httpx.AsyncClient(base_url=self._s.procore_base_url, timeout=60) as client:
            while True:
                params["page"] = page
                resp = await client.get(path, params=params, headers=headers)
                resp.raise_for_status()
                rows = resp.json()
                if not isinstance(rows, list):
                    rows = rows.get("data", [])
                items.extend(rows)
                if len(rows) < params["per_page"] or not rows:
                    break
                page += 1
        return items

    # -- jobs domain -------------------------------------------------------------------
    # Endpoints below are the documented Procore REST v1.0 paths. Fill the row->model mapping against a
    # real tenant (verify field names and units first). `{company}` is PROCORE_COMPANY_ID.

    async def get_jobs(self, as_of: date) -> list[DispatchJob]:
        # GET /rest/v1.0/projects?company_id={company} -> DispatchJob (project the project address).
        raise NotImplementedError(
            "Map Procore projects -> DispatchJob "
            "(projects domain; verify address -> zone coords + active filter)."
        )

    # -- documents domain --------------------------------------------------------------

    async def get_documents(self, as_of: date) -> list[Document]:
        # GET /rest/v1.0/projects/{project}/rfis (+ /submittals, /daily_logs) -> Document.
        raise NotImplementedError(
            "Map Procore RFIs/submittals/daily-logs -> Document "
            "(documents domain; verify e-sign/expiry/amount extraction)."
        )

    async def get_customers(self) -> list[KnownCustomer]:
        # GET /rest/v1.0/companies/{company}/vendors (+ project contacts) -> KnownCustomer.
        raise NotImplementedError(
            "Map Procore vendors/contacts -> KnownCustomer (documents domain match key)."
        )

    # -- accounting domain -------------------------------------------------------------

    async def get_ar_invoices(self) -> list[ARInvoice]:
        # GET /rest/v1.0/projects/{project}/prime_contracts (+ owner invoices) -> ARInvoice.
        raise NotImplementedError(
            "Map Procore prime-contracts/owner-invoices -> ARInvoice "
            "(budgets/prime-contracts/change-orders domain; verify issued/due/paid)."
        )

    async def get_ap_bills(self) -> list[APBill]:
        # GET /rest/v1.0/projects/{project}/commitments (subcontracts/POs + change orders) -> APBill.
        raise NotImplementedError(
            "Map Procore commitments/change-orders -> APBill "
            "(budgets/prime-contracts/change-orders domain; verify vendor + due + amount units)."
        )
