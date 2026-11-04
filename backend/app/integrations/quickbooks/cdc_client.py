"""QuickBooks Online Change Data Capture (CDC) poll client (ADR 0010).

`GET /v3/company/{realm}/cdc?entities=...&changedSince=...` is the REQUIRED completeness path for
QBO detection: `Attachable` (receipt images) fires **no** webhook, so it must be polled. The default
entity list therefore always includes `Attachable`.

Auth reuses `QuickBooksClient` verbatim (OAuth2 refresh-token `_access_token` + throttle-aware `_get`).
FAIL CLOSED (ADR 0005): every call requires the connected-company credential set (client id/secret +
the vaulted refresh token + realm id from `qbo_connection`) — no connected company, no feed, never a
fabricated row. Response parsing is a pure function so the shape contract is pinned by unit tests
before a live realm exists.
"""
from __future__ import annotations

import datetime as dt

from app.integrations.accounting.quickbooks_client import QuickBooksClient
from app.sync import normalize

# QBO CDC accepts changedSince up to 30 days back; a fresh cursor anchors a bounded lookback.
DEFAULT_LOOKBACK_DAYS = 7

# PascalCase QBO entity names eligible for our CDC poll. Ordered so the preferred name wins when two
# map to the same canonical entity (Payment before BillPayment). MUST include Attachable (no webhook).
DEFAULT_CDC_ENTITIES: tuple[str, ...] = (
    "Bill",
    "Purchase",
    "Payment",
    "BillPayment",
    "Invoice",
    "JournalEntry",
    "PurchaseOrder",
    "VendorCredit",
    "Vendor",
    "Customer",
    "Item",
    "Deposit",
    "Attachable",
)

# canonical sync entity -> the QBO CDC entity name to poll for it (reverse of normalize._QBO_ENTITY,
# derived through the public mapper so the two can never drift; first eligible name wins).
QBO_ENTITY_FOR: dict[str, str] = {}
for _name in DEFAULT_CDC_ENTITIES:
    _canonical = normalize.canonical_qbo_entity(_name)
    if _canonical is not None:
        QBO_ENTITY_FOR.setdefault(_canonical, _name)


def qbo_entity_for(entity: str) -> str | None:
    """The QBO CDC entity name serving canonical `entity`, or None if the entity is not mapped."""
    return QBO_ENTITY_FOR.get(entity)


def parse_cdc_response(body: dict) -> list[tuple[str, dict]]:
    """Pure: Intuit's CDC envelope -> `[(qbo_entity_name, row), ...]`.

    Shape: `{"CDCResponse": [{"QueryResponse": [{"Bill": [rows...]}, {"Attachable": [rows...]}]}]}`.
    Non-row keys (`startPosition`, `maxResults`, `totalCount`) are skipped; unknown shapes yield
    nothing rather than a guess.
    """
    rows: list[tuple[str, dict]] = []
    for cdc in body.get("CDCResponse") or []:
        if not isinstance(cdc, dict):
            continue
        for query_response in cdc.get("QueryResponse") or []:
            if not isinstance(query_response, dict):
                continue
            for key, value in query_response.items():
                if not isinstance(value, list):
                    continue
                rows.extend((key, row) for row in value if isinstance(row, dict))
    return rows


class QuickBooksCdcClient(QuickBooksClient):
    """The CDC poll surface. Inherits the accounting client's credential gate + token refresh + 429
    backoff, so the change feed and the report reads share one auth path."""

    async def fetch_cdc(
        self,
        entities: list[str] | tuple[str, ...] | None = None,
        changed_since: str | None = None,
    ) -> list[tuple[str, dict]]:
        """Poll changed entities since the persisted watermark: `[(qbo_entity_name, row), ...]`.

        `changed_since` is the `sync_cursor.cursor_token` (None = a bounded default lookback); the
        caller advances its cursor to the max `MetaData.LastUpdatedTime` seen only AFTER the batch is
        durably enqueued (ADR-0010 §4).
        """
        self._require()  # fail closed before any network call (ADR 0005)
        names = list(entities) if entities else list(DEFAULT_CDC_ENTITIES)
        if changed_since is None:
            anchor = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=DEFAULT_LOOKBACK_DAYS)
            changed_since = anchor.strftime("%Y-%m-%dT%H:%M:%SZ")
        body = await self._get(
            f"/v3/company/{self._realm_id}/cdc",
            {"entities": ",".join(names), "changedSince": changed_since},
        )
        return parse_cdc_response(body)
