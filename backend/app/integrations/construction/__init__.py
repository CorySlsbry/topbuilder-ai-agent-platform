"""Construction-platform adapters (Buildertrend, Procore).

The platform is provider-agnostic: agents consume CANONICAL domain models and each platform maps onto
them through an adapter. Construction platforms serve the `jobs`, `documents`, and `accounting` domains
only (NOT intake/inventory — those tenants keep their existing sources). These live clients are
fail-closed skeletons, exactly as `app/integrations/servicetitan/` is: auth + paginator + credential
gating are real and testable; the per-endpoint response mapping is filled against a real tenant at
go-live (ADR 0005). `dispatch.get_construction_client` / `get_fsm_live_client` are the one adapter-layer
dispatcher that routes a provider slug to the right live client.
"""
from __future__ import annotations
