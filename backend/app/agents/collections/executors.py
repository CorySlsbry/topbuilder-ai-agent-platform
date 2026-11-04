"""Action executors for the Collections agent's dunning sends (ADR 0007), kept in the agent package
so they're owned + tested here; the shared ``app/actions/executors.py`` registry imports + registers
them (and their undos). Each performs the WRITE for an approved dunning step:

  * ``send_dunning_email`` — send the drafted dunning email (fixture: deterministic confirmation;
    live: via the email/Workspace adapter, fail-closed).
  * ``send_dunning_sms``   — send the drafted SMS via the provider-agnostic VoiceClient.
  * ``place_dunning_call`` — place the outbound call (script) via the provider-agnostic VoiceClient.

Undo / compensation (autonomous-with-undo): a sent message can't be unsent, so the compensation logs a
retraction / marks the outreach not-sent (mirrors ``_undo_send_email_reply``). Promise-to-pay capture is
a separate, non-destructive recorded action (no external write) — recorded directly, not through a send.

VoIP is provider-agnostic (Cory's call): the SMS/call go through ``app.voice.voice_client`` (simulated
by default, fail-closed live skeleton) — never a Twilio/RingCentral hardcode. Compliance (TCPA/quiet
hours/opt-out) was already enforced upstream by the engine's channel choice + the draft copy.
"""
from __future__ import annotations

from app.actions.executors import ActionError
from app.config import Settings
from app.voice.voice_client import VoiceProviderError, get_voice_client


async def send_dunning_email(params: dict, settings: Settings) -> dict:
    customer_id = params.get("customer_id")
    if not customer_id:
        raise ActionError("send_dunning_email requires 'customer_id'")
    if not params.get("email_body"):
        raise ActionError("send_dunning_email requires a drafted 'email_body'")
    if settings.email_mode.lower() == "live":
        raise ActionError(
            "live dunning email send is not yet wired; implement via the Gmail/Workspace adapter (ADR 0005)."
        )
    return {
        "system": "email", "mode": "fixture", "external_ref": f"dun-email-{customer_id}",
        "customer_id": customer_id, "channel": "email", "dunning_step": params.get("dunning_step"),
        "subject": params.get("email_subject"), "status": "sent",
    }


async def send_dunning_sms(params: dict, settings: Settings) -> dict:
    customer_id = params.get("customer_id")
    if not customer_id:
        raise ActionError("send_dunning_sms requires 'customer_id'")
    body = params.get("sms_body")
    if not body:
        raise ActionError("send_dunning_sms requires a drafted 'sms_body'")
    client = get_voice_client(settings)
    try:
        res = await client.send_sms(
            to=str(params.get("phone") or customer_id),
            body=body,
            idempotency_key=f"dun-sms-{customer_id}-{params.get('dunning_step')}",
        )
    except VoiceProviderError as exc:
        raise ActionError(str(exc)) from exc
    return {
        "system": "sms", "mode": res.mode, "provider": res.provider, "external_ref": res.external_ref,
        "customer_id": customer_id, "channel": "sms", "dunning_step": params.get("dunning_step"),
        "status": "sent" if res.status in ("sent", "queued") else res.status,
    }


async def place_dunning_call(params: dict, settings: Settings) -> dict:
    customer_id = params.get("customer_id")
    if not customer_id:
        raise ActionError("place_dunning_call requires 'customer_id'")
    script = params.get("call_script")
    if not script:
        raise ActionError("place_dunning_call requires a drafted 'call_script'")
    client = get_voice_client(settings)
    try:
        res = await client.place_call(
            to=str(params.get("phone") or customer_id),
            script=script,
            idempotency_key=f"dun-call-{customer_id}-{params.get('dunning_step')}",
        )
    except VoiceProviderError as exc:
        raise ActionError(str(exc)) from exc
    return {
        "system": "voice", "mode": res.mode, "provider": res.provider, "external_ref": res.external_ref,
        "customer_id": customer_id, "channel": "call", "dunning_step": params.get("dunning_step"),
        "status": "placed" if res.status in ("placed", "queued") else res.status,
    }


# --- undo / compensation (a sent message can't be unsent -> log a retraction / mark not-sent) ----
async def undo_send_dunning_email(params: dict, result: dict, settings: Settings) -> dict:
    return {"system": "email", "external_ref": result.get("external_ref"), "status": "retraction_logged"}


async def undo_send_dunning_sms(params: dict, result: dict, settings: Settings) -> dict:
    return {"system": "sms", "external_ref": result.get("external_ref"), "status": "marked_not_sent"}


async def undo_place_dunning_call(params: dict, result: dict, settings: Settings) -> dict:
    return {"system": "voice", "external_ref": result.get("external_ref"), "status": "call_retraction_logged"}
