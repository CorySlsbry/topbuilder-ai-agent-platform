"""ServiceTitan `/export` change-feed client (ADR 0010) — the poll-backbone detector.

One page of the canonical change-detection primitive: `GET /{module}/v2/tenant/{t}/export/{entity}`
with the persisted continuation token as `from`, returning `(rows, new_continue_from, has_more)`.
The poll service enqueues each page and advances its `sync_cursor` to the returned token, so a crashed
tick resumes gap-free at page granularity.

Auth reuses `LiveServiceTitanClient` verbatim (OAuth2 client-credentials `_access_token` + `_headers`),
so the token cache and credential handling never drift between the run-time reads and the change feed.
FAIL CLOSED (ADR 0005): every call requires the full ServiceTitan credential set — no creds, no feed,
never a fabricated row. Only entities the sync layer (`app/sync/normalize.py`) handles are mapped;
an unmapped entity refuses rather than guessing an endpoint.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.integrations.servicetitan.live_client import LiveServiceTitanClient

# canonical sync entity -> (ServiceTitan API module, export path segment). Restricted to entities
# `app/sync/normalize.py` + `app/sync/router.py` handle (every polled entity is routable — nothing
# is pulled just to no_route at drain) AND that have a documented `/export` feed. Entities without
# an export feed (pricebook_*, attachment) use the modified-since fallback (Phase 2).
EXPORT_ENTITIES: dict[str, tuple[str, str]] = {
    # Accounting / AP / AR
    "bill": ("accounting", "inventory-bills"),  # ST vendor bills = "inventory bills"
    "invoice": ("accounting", "invoices"),
    "payment": ("accounting", "payments"),
    # Jobs / dispatch
    "job": ("jpm", "jobs"),
    "appointment": ("jpm", "appointments"),
    # CRM
    "booking": ("crm", "bookings"),
    "lead": ("crm", "leads"),
    "customer": ("crm", "customers"),
    # Inventory
    "purchase_order": ("inventory", "purchase-orders"),
    "po_receipt": ("inventory", "receipts"),
    "inventory_return": ("inventory", "returns"),
    "inventory_adjustment": ("inventory", "adjustments"),
    "inventory_transfer": ("inventory", "transfers"),
    # Payroll
    "timesheet": ("payroll", "jobs/timesheets"),
    "gross_pay_item": ("payroll", "gross-pay-items"),
    "payroll_adjustment": ("payroll", "payroll-adjustments"),
}


def export_module_for(entity: str) -> str | None:
    """The ST API module serving `entity`'s export feed, or None if no feed is mapped."""
    mapped = EXPORT_ENTITIES.get(entity)
    return mapped[0] if mapped else None


class ServiceTitanExportClient(LiveServiceTitanClient):
    """The change-feed read surface. Inherits the live client's credential gate + OAuth2 token flow."""

    async def fetch_export_page(
        self, module: str, entity: str, continue_from: str | None
    ) -> tuple[list[dict], str | None, bool]:
        """One export page: `(rows, new_continue_from, has_more)`.

        `continue_from` is the persisted `sync_cursor.cursor_token` (None = from origin); the caller
        stores the returned token only AFTER the page's rows are durably enqueued (ADR-0010 §4).
        """
        self._require_credentials()  # fail closed before any network call (ADR 0005)
        mapped = EXPORT_ENTITIES.get(entity)
        if mapped is None:
            raise RuntimeError(f"no ServiceTitan export feed mapped for entity '{entity}'")
        expected_module, segment = mapped
        if module != expected_module:
            raise RuntimeError(
                f"entity '{entity}' exports under module '{expected_module}', not '{module}'"
            )
        headers = await self._headers()
        params: dict[str, Any] = {}
        if continue_from:
            params["from"] = continue_from
        path = f"/{expected_module}/v2/tenant/{self._s.servicetitan_tenant_id}/export/{segment}"
        async with httpx.AsyncClient(base_url=self._s.servicetitan_base_url, timeout=60) as client:
            resp = await client.get(path, params=params, headers=headers)
            resp.raise_for_status()
            body = resp.json()
        return (
            list(body.get("data") or []),
            body.get("continueFrom"),
            bool(body.get("hasMore")),
        )
