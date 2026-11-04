"""Live ServiceTitan client — OAuth2 client-credentials skeleton.

The auth flow and paginator are fully implemented (and unit-testable). The per-endpoint response
mapping is intentionally left to be filled against a real tenant, because the exact field shapes
and units must be verified with live data rather than guessed — see ADR 0005. Selected via
`SERVICETITAN_MODE=live`.
"""
from __future__ import annotations

import time
from datetime import date
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.agents.workforce.models import (
    Appointment,
    DemandSignal,
    JobDurationStat,
    Technician,
    Timesheet,
    TradeEconomics,
)
from app.config import Settings


class LiveServiceTitanClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._token: str | None = None
        self._token_expiry_monotonic: float = 0.0

    def _require_credentials(self) -> None:
        missing = [
            name
            for name, value in {
                "SERVICETITAN_CLIENT_ID": self._s.servicetitan_client_id,
                "SERVICETITAN_CLIENT_SECRET": self._s.servicetitan_client_secret,
                "SERVICETITAN_APP_KEY": self._s.servicetitan_app_key,
                "SERVICETITAN_TENANT_ID": self._s.servicetitan_tenant_id,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                "ServiceTitan live mode requires: " + ", ".join(missing)
            )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=8))
    async def _access_token(self) -> str:
        self._require_credentials()
        now = time.monotonic()
        if self._token is not None and now < self._token_expiry_monotonic - 60:
            return self._token
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self._s.servicetitan_auth_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._s.servicetitan_client_id,
                    "client_secret": self._s.servicetitan_client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            token = resp.json()
        self._token = token["access_token"]
        self._token_expiry_monotonic = now + float(token.get("expires_in", 900))
        return self._token

    async def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {await self._access_token()}",
            "ST-App-Key": self._s.servicetitan_app_key or "",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=8))
    async def _get_paginated(self, path: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Follow ServiceTitan's `hasMore`/`continueFrom` pagination, returning all `data` rows."""
        headers = await self._headers()
        params = dict(params or {})
        params.setdefault("pageSize", 200)
        items: list[dict] = []
        async with httpx.AsyncClient(base_url=self._s.servicetitan_base_url, timeout=60) as client:
            while True:
                resp = await client.get(path, params=params, headers=headers)
                resp.raise_for_status()
                body = resp.json()
                items.extend(body.get("data", []))
                if not body.get("hasMore"):
                    break
                params["continueFrom"] = body.get("continueFrom")
        return items

    # -- read surface ------------------------------------------------------------------
    # Endpoints below are the documented ServiceTitan paths. Fill the row->model mapping
    # against a real tenant (verify field names and units first). `{tenant}` is the ST tenant id.

    async def get_technicians(self) -> list[Technician]:
        # GET /settings/v2/tenant/{tenant}/technicians
        raise NotImplementedError(
            "Map ServiceTitan technicians -> Technician (verify hourlyCost/burdenedCost units)."
        )

    async def get_trade_economics(self) -> list[TradeEconomics]:
        # Derived from pricebook/business-unit billing rates; no single ST endpoint.
        raise NotImplementedError("Derive TradeEconomics from ST pricebook + business units.")

    async def get_appointments(self, start: date, end: date) -> list[Appointment]:
        # GET /jpm/v2/tenant/{tenant}/appointments  (verify param names + trade/jobType source)
        from app.integrations.servicetitan.mappers import map_appointment

        rows = await self._get_paginated(
            f"/jpm/v2/tenant/{self._s.servicetitan_tenant_id}/appointments",
            {"startsOnOrAfter": start.isoformat(), "startsBefore": end.isoformat()},
        )
        return [map_appointment(row) for row in rows]

    async def get_timesheets(self, start: date, end: date) -> list[Timesheet]:
        # GET /payroll/v2/tenant/{tenant}/timesheets  (or gross-pay items)
        from app.integrations.servicetitan.mappers import map_timesheet

        rows = await self._get_paginated(
            f"/payroll/v2/tenant/{self._s.servicetitan_tenant_id}/timesheets",
            {"dateOnOrAfter": start.isoformat(), "dateBefore": end.isoformat()},
        )
        return [map_timesheet(row) for row in rows]

    async def get_job_durations(self) -> list[JobDurationStat]:
        # Aggregate historical completed jobs (GET /jpm/v2/.../jobs) by job type.
        raise NotImplementedError("Aggregate historical job durations -> JobDurationStat.")

    async def get_demand_signals(self) -> list[DemandSignal]:
        # Blend ST booking velocity with a seasonal/weather model.
        raise NotImplementedError("Compute DemandSignal from ST booking trend + seasonality.")
