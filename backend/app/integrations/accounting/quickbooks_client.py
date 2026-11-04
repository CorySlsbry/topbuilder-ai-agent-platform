"""Live QuickBooks Online client — OAuth2 refresh-token + first-party Reports/Query reads (ADR 0005).

Token refresh is implemented; each read method now BUILDS the exact Intuit request (via the pure
``quickbooks_reports`` builders) and PARSES the response into the existing cents-based domain shapes
(via the pure ``quickbooks_reports`` parsers). The actual HTTP is gated behind the connected-credential
check (``_require``): without a realm id + refresh token (the demo), every read raises the fail-closed
error — it never fabricates a figure (ADR-0005 raise-not-fabricate). Selected by
``ACCOUNTING_MODE=quickbooks``.

The request CONSTRUCTION and response PARSING are unit-tested on saved sample-report fixtures with no
network (``tests/test_quickbooks_reports.py``) — so the live mapping is pinned before a realm exists.
Going live wires only the credential persistence (realmId + rotated refresh token) and flips the mode;
the request/parse contract here does not change.

Money note (ADR-0003): the parsers carry integer **cents**; the legacy Financial-agent domain models
(``ARInvoice``/``APBill``/``CompanyFinancials``) carry float **dollars**, so this adapter converts
cents -> dollars at the boundary where it builds those models.
"""
from __future__ import annotations

import base64
import time
from datetime import date, timedelta

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.agents.financial.models import (
    APBill,
    ARInvoice,
    CompanyFinancials,
    Job,
    PaymentVelocity,
)
from app.config import Settings
from app.integrations.accounting import quickbooks_reports as qr


def _is_throttle(exc: BaseException) -> bool:
    """Retry only on HTTP 429 (Intuit ThrottleExceeded) — leave 4xx auth errors to fail fast."""
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


class QuickBooksClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._token: str | None = None
        self._expiry_monotonic = 0.0

    def _require(self) -> None:
        missing = [
            name
            for name, value in {
                "QUICKBOOKS_CLIENT_ID": self._s.quickbooks_client_id,
                "QUICKBOOKS_CLIENT_SECRET": self._s.quickbooks_client_secret,
                "QUICKBOOKS_REFRESH_TOKEN": self._s.quickbooks_refresh_token,
                "QUICKBOOKS_REALM_ID": self._s.quickbooks_realm_id,
            }.items()
            if not value
        ]
        if missing:
            # Fail closed (ADR-0005): no connected company -> raise, never fabricate a figure.
            raise RuntimeError("QuickBooks mode requires: " + ", ".join(missing))

    @property
    def _realm_id(self) -> str:
        self._require()
        return str(self._s.quickbooks_realm_id)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=8))
    async def _access_token(self) -> str:
        self._require()
        if self._token and time.monotonic() < self._expiry_monotonic - 60:
            return self._token
        basic = base64.b64encode(
            f"{self._s.quickbooks_client_id}:{self._s.quickbooks_client_secret}".encode()
        ).decode()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self._s.quickbooks_token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._s.quickbooks_refresh_token,
                },
                headers={
                    "Authorization": f"Basic {basic}",
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            resp.raise_for_status()
            token = resp.json()
        self._token = token["access_token"]
        self._expiry_monotonic = time.monotonic() + float(token.get("expires_in", 3600))
        # NOTE (go-live): Intuit ROTATES the refresh token on each use. The caller must persist the
        # returned `token["refresh_token"]` (and realmId) to the per-tenant vault here — see
        # docs/QBO_DATA_MAP.md §1.2. A stale un-persisted refresh token is the #1 "disconnected" cause.
        return self._token

    @retry(
        retry=retry_if_exception(_is_throttle),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=8),
    )
    async def _get(self, path: str, params: dict[str, str]) -> dict:
        """GET a built (path, params) against the QBO API base, with 429 backoff. JSON in, JSON out."""
        headers = {
            "Authorization": f"Bearer {await self._access_token()}",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(base_url=self._s.quickbooks_base_url, timeout=60) as client:
            resp = await client.get(path, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()

    # -- read surface ------------------------------------------------------------------
    # Each method builds the §2 request, fetches (gated), and parses into the domain shape.

    async def get_company_financials(self) -> CompanyFinancials:
        # BalanceSheet -> cash; P&L -> target gross margin. cents -> dollars at the boundary.
        bs_path, bs_params = qr.build_balance_sheet_request(self._realm_id, date_macro="Today")
        balance_sheet = qr.parse_balance_sheet(await self._get(bs_path, bs_params))
        pl_path, pl_params = qr.build_profit_and_loss_request(self._realm_id)
        pl = qr.parse_profit_and_loss(await self._get(pl_path, pl_params))
        margin = pl.gross_margin_ratio
        return CompanyFinancials(
            starting_cash=balance_sheet.cash_cents / 100,
            target_gross_margin=margin if margin is not None else 0.0,
        )

    async def get_jobs(self) -> list[Job]:
        # QBO Projects / job-costing has no single report mapped here; jobs/WIP are primarily a
        # ServiceTitan surface (QBO_DATA_MAP §2.1: average_job_size is ST-sourced, QBO cross-checks).
        raise NotImplementedError("Map QBO Projects/job-costing -> Job (WIP fields).")

    async def get_ar_invoices(self) -> list[ARInvoice]:
        # Query open invoices -> ARInvoice (Balance > 0). cents -> dollars at the boundary.
        path, params = qr.build_open_invoices_query(self._realm_id)
        invoices = qr.parse_invoice_query(await self._get(path, params))
        return [
            ARInvoice(
                id=inv.id,
                customer_segment=inv.customer or "unknown",
                amount=inv.balance_cents / 100,
                issued=inv.txn_date or date.today(),
                due=inv.due_date or (inv.txn_date or date.today()),
                paid=False,
            )
            for inv in invoices
        ]

    async def get_ap_bills(self) -> list[APBill]:
        # Query open bills -> APBill (Balance > 0). cents -> dollars at the boundary.
        path, params = qr.build_open_bills_query(self._realm_id)
        bills = qr.parse_bill_query(await self._get(path, params))
        return [
            APBill(
                id=bill.id,
                vendor=bill.vendor or "unknown",
                amount=bill.balance_cents / 100,
                due=bill.due_date or (bill.txn_date or date.today()),
                paid=False,
            )
            for bill in bills
        ]

    async def get_payment_velocity(self) -> list[PaymentVelocity]:
        # Derived from payment history. The trailing-window Payment query gives received cash; a robust
        # avg-days-to-pay needs the paid-invoice join (Invoice.LinkedTxn), verified against a live
        # company (ADR-0005) — left as a go-live mapping rather than a guessed approximation.
        raise NotImplementedError("Compute PaymentVelocity from QBO payment history (Invoice<->Payment join).")
