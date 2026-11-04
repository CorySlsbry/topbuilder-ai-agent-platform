"""Provider-agnostic voice + SMS client (Cory's call: assume VoIP everywhere, no provider lock-in).

A thin abstraction so the Collections agent (and any future telephony surface) can place an outbound
dunning CALL or send an SMS without binding to Twilio / RingCentral / Telnyx / Vonage. The shape mirrors
the rest of the codebase's adapter boundaries:

  * ``VoiceClient`` — the Protocol every provider implements (``place_call`` / ``send_sms``).
  * ``SimulatedVoiceClient`` — a deterministic, offline impl (the default; used by the action-gate
    fixture executors so the whole propose->approve->execute path is testable with no carrier).
  * ``LiveVoiceClient`` — a typed, FAIL-CLOSED skeleton (ADR 0005): it raises rather than fabricate a
    placed call / sent message until wired against a real provider behind verified credentials.

Compliance note (TCPA/quiet-hours) lives one layer up in the engine (``downgrade_for_compliance``) and
the drafts (opt-out copy); this layer only transports the already-compliant message.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.config import Settings, get_settings


class VoiceProviderError(Exception):
    """Raised when a call/SMS cannot be placed (unconfigured, fail-closed live, upstream failure)."""


@dataclass(frozen=True)
class CallResult:
    provider: str
    mode: str  # simulated | live
    external_ref: str  # the provider call id (or a deterministic sim id)
    to: str
    status: str  # placed | queued | failed


@dataclass(frozen=True)
class SmsResult:
    provider: str
    mode: str
    external_ref: str
    to: str
    status: str  # sent | queued | failed


@runtime_checkable
class VoiceClient(Protocol):
    """The minimal outbound surface the Collections dunning path needs."""

    async def place_call(self, *, to: str, script: str, idempotency_key: str) -> CallResult: ...
    async def send_sms(self, *, to: str, body: str, idempotency_key: str) -> SmsResult: ...


class SimulatedVoiceClient:
    """Deterministic, carrier-free impl. No randomness so the action gate is offline-testable."""

    provider = "simulated"

    async def place_call(self, *, to: str, script: str, idempotency_key: str) -> CallResult:
        return CallResult(
            provider=self.provider, mode="simulated",
            external_ref=f"sim-call-{idempotency_key}", to=to, status="placed",
        )

    async def send_sms(self, *, to: str, body: str, idempotency_key: str) -> SmsResult:
        return SmsResult(
            provider=self.provider, mode="simulated",
            external_ref=f"sim-sms-{idempotency_key}", to=to, status="sent",
        )


class LiveVoiceClient:
    """Fail-closed live skeleton (ADR 0005): raises until wired to a real VoIP provider.

    Wiring point: read the provider + credentials from the per-tenant vault, POST the call/SMS to the
    provider's REST API, return its message id as ``external_ref``. Never fabricate a placed call.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.provider = (getattr(settings, "voice_provider", None) or "unconfigured").lower()

    async def place_call(self, *, to: str, script: str, idempotency_key: str) -> CallResult:
        raise VoiceProviderError(
            "live outbound call is not yet wired; implement against the configured VoIP provider's "
            "REST API behind verified per-tenant credentials (ADR 0005)."
        )

    async def send_sms(self, *, to: str, body: str, idempotency_key: str) -> SmsResult:
        raise VoiceProviderError(
            "live outbound SMS is not yet wired; implement against the configured VoIP/SMS provider's "
            "REST API behind verified per-tenant credentials (ADR 0005)."
        )


def get_voice_client(settings: Settings | None = None) -> VoiceClient:
    """Factory: simulated by default (offline-safe); live skeleton when ``voice_mode=live``."""
    settings = settings or get_settings()
    if getattr(settings, "voice_mode", "fixture").lower() == "live":
        return LiveVoiceClient(settings)
    return SimulatedVoiceClient()
