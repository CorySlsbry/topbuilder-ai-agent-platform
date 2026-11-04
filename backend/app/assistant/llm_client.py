"""The single place the assistant constructs its Anthropic client — built INFERENCE-ONLY by design.

The in-app assistant (`service.py`) is the only live-LLM path in the running product: `DISABLE_LLM=1`
keeps every deterministic agent's narration on its template renderer (see each `agents/*/reasoning.py`)
and the self-learning loop never calls a model on the request path. So this helper is where the
platform's external-LLM data posture is pinned and documented.

Posture (truthful, and the reason this module exists — see `docs/AI_DATA_HANDLING.md`):

- **Inference only, never training.** Calls to the Anthropic Messages API are used to NARRATE results
  that deterministic code already computed (ADR 0003: the figure firewall — the model never produces a
  business number). Anthropic's commercial API does not train models on API inputs or outputs; nothing
  in this client opts INTO any training/feedback program, and there is no such setting to enable here.
- **Stateless per request.** Each `messages.create` carries the whole conversation; the model retains
  no customer/ServiceTitan/QuickBooks data between requests. The only persistence is OUR RLS-isolated
  Postgres (per-tenant), never the model.
- **No-retention hint, when the account supports it.** If `anthropic_zero_retention` is set, we send
  the documented opt-out header so request/response bodies are not retained beyond serving the call.
  It defaults OFF (no-op) because zero-data-retention is an account-level entitlement — turning it on
  in code without it provisioned would just be sent and ignored, or rejected; we surface it as a flag
  the operator flips once Anthropic enables it on the production account. Either way the no-TRAINING
  guarantee above holds regardless of this header.

Nothing here changes behaviour when the flags are at their defaults: with no key the assistant 503s
upstream (`service.chat`), and with the defaults the client is byte-for-byte the prior plain client.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid importing the SDK at module import time (keeps pure tests dependency-free)
    from anthropic import AsyncAnthropic

    from app.config import Settings


# The documented opt-out header for accounts entitled to zero data retention. Kept as a constant so a
# single edit moves it if Anthropic renames it; only emitted when the operator turns the flag on.
ZERO_RETENTION_HEADER = "anthropic-no-retention"

# Network resilience defaults applied to EVERY AsyncAnthropic we build (assistant + every reasoning
# module + the eval harness). A narration call must never hang a run: a hard request timeout plus a
# small retry budget bounds the worst case, and every reasoning `explain()` already falls back to its
# deterministic template if the call ultimately fails. Centralizing these here means one edit changes
# the posture everywhere instead of per-call-site drift.
LLM_TIMEOUT_SECONDS = 35.0
LLM_MAX_RETRIES = 2


def inference_only_headers(settings: "Settings") -> dict[str, str]:
    """The default headers that encode our external-LLM posture. Pure + table-testable (no SDK, no IO).

    Returns the no-retention opt-out header ONLY when the operator has flipped the (default-off) flag,
    so the production default is an empty dict — i.e. the client is unchanged unless explicitly opted in.
    There is deliberately NO "enable training" header: the inference-only / no-train posture is the
    Anthropic commercial-API default and we never opt out of it.
    """
    headers: dict[str, str] = {}
    if getattr(settings, "anthropic_zero_retention", False):
        headers[ZERO_RETENTION_HEADER] = "true"
    return headers


def build_llm_client(settings: "Settings") -> "AsyncAnthropic":
    """The ONE place an `AsyncAnthropic` is constructed for this platform (assistant + reasoning + eval).

    Applies the full posture in one shot: the inference-only / no-retention headers, an explicit 35s
    request timeout, and a 2-retry budget. Every reasoning `explain()` and the eval harness route their
    SDK construction through here so timeout/retry/header behavior can never drift between call sites.

    Callers must have already checked `settings.anthropic_api_key`; this helper does not invent a key.
    Importing the SDK is deferred to call time so importing this module (and the pure tests that exercise
    `inference_only_headers`) never requires `anthropic` installed.
    """
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        default_headers=inference_only_headers(settings),
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )


# Backwards-compatible alias: the assistant constructs its client by this name. It is now the same
# fully-configured client every other LLM path uses (timeout + retries + inference-only headers).
build_assistant_client = build_llm_client
