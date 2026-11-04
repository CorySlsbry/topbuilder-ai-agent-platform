"""The one adapter-layer dispatcher — provider slug -> the right live client.

`get_construction_client` returns the construction live client (Buildertrend / Procore).
`get_fsm_live_client` is the wider router that ALSO routes `servicetitan` to the existing
`LiveServiceTitanClient`, so a caller can resolve any field-system slug through one entry point.

Fail-closed: an unknown or unsupported slug raises `ValueError` — the dispatcher never silently
returns a default client (which would point a tenant at the wrong system's data).
"""
from __future__ import annotations

from app.config import Settings
from app.integrations.construction.buildertrend_client import LiveBuildertrendClient
from app.integrations.construction.procore_client import LiveProcoreClient

# Construction-segment slugs -> their live client class (mirrors the registry's `segment`).
_CONSTRUCTION_CLIENTS = {
    "buildertrend": LiveBuildertrendClient,
    "procore": LiveProcoreClient,
}


def get_construction_client(
    provider_slug: str, settings: Settings
) -> LiveBuildertrendClient | LiveProcoreClient:
    """Return the construction live client for `buildertrend` / `procore`; raise for anything else."""
    slug = (provider_slug or "").strip().lower()
    client_cls = _CONSTRUCTION_CLIENTS.get(slug)
    if client_cls is None:
        raise ValueError(
            f"No construction adapter for provider {provider_slug!r}; "
            f"supported: {sorted(_CONSTRUCTION_CLIENTS)}"
        )
    return client_cls(settings)


def get_fsm_live_client(provider_slug: str, settings: Settings):
    """Resolve ANY field-system slug to its live client (construction + ServiceTitan).

    Imports the ServiceTitan client lazily so this module stays cheap and the construction package has
    no hard dependency on the ServiceTitan package at import time.
    """
    slug = (provider_slug or "").strip().lower()
    if slug == "servicetitan":
        from app.integrations.servicetitan.live_client import LiveServiceTitanClient

        return LiveServiceTitanClient(settings)
    if slug in _CONSTRUCTION_CLIENTS:
        return get_construction_client(slug, settings)
    raise ValueError(
        f"No live FSM adapter for provider {provider_slug!r}; "
        f"supported: {sorted({'servicetitan', *_CONSTRUCTION_CLIENTS})}"
    )
