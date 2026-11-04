"""Action executor for the Pricebook agent's price write-back (ADR 0007), kept in the agent package so
it's owned + tested here; the shared ``app/actions/executors.py`` registry imports + registers it (and
its undo).

  * ``update_pricebook_item`` — write the recomputed price to a ServiceTitan Pricebook item (fixture:
    deterministic confirmation; live: via the ST Pricebook update API, fail-closed until verified).

Undo / compensation: restore the prior price (the action params carry ``old_price_cents`` so the reversal
is a deterministic restore, not a fabricated value). Pricebook prices are customer-facing, so this kind is
ALWAYS human-in-the-loop (see ``ALWAYS_HITL_KINDS`` in app/actions/service.py) — never auto-executed.
"""
from __future__ import annotations

from app.actions.executors import ActionError
from app.config import Settings


async def update_pricebook_item(params: dict, settings: Settings) -> dict:
    code = params.get("code")
    if not code:
        raise ActionError("update_pricebook_item requires 'code'")
    if params.get("new_price_cents") is None:
        raise ActionError("update_pricebook_item requires a 'new_price_cents'")
    if settings.servicetitan_mode.lower() == "live":
        # PATCH the new price onto the ServiceTitan Pricebook item via the live client (the human
        # approval is already recorded on the action). Typed skeleton — fail-closed until verified
        # against a real tenant (ADR 0005/0007). Never write, never fabricate a success.
        raise ActionError(
            "live ServiceTitan pricebook update is not yet wired; implement against the ST "
            "pricebook/v2 update API behind the live adapter (ADR 0005/0007)."
        )
    new_price_cents = int(params.get("new_price_cents") or 0)
    old_price_cents = int(params.get("old_price_cents") or 0)
    return {
        "system": "servicetitan",
        "mode": "fixture",
        "external_ref": f"st-pricebook-{code}",
        "code": code,
        "name": params.get("name"),
        "old_price_usd": round(old_price_cents / 100, 2),
        "new_price_usd": round(new_price_cents / 100, 2),
        "status": "price_updated",
    }


async def undo_update_pricebook_item(params: dict, result: dict, settings: Settings) -> dict:
    """Restore the prior price (a deterministic restore from the approved params)."""
    old_price_cents = int(params.get("old_price_cents") or 0)
    return {
        "system": "servicetitan",
        "external_ref": result.get("external_ref"),
        "code": result.get("code") or params.get("code"),
        "restored_price_usd": round(old_price_cents / 100, 2),
        "status": "price_restored",
    }
