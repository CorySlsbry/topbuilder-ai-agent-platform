"""The booking agent's phone-voice registry — the voices that answer a tenant's calls 24/7.

Three production-quality, non-robotic voices (ElevenLabs premade library), branded with product
persona names. Selection is per-tenant (`tenant_settings.booking_voice`, migration 0016) with Riley
as the default. `preview_url` points at a real synthesized conversation sample bundled with the
dashboard (`frontend/public/voices/<key>.mp3`) so a buyer hears exactly what their callers will
hear; the live telephony layer reads `elevenlabs_voice_id` for the same voice at call time.

Synthesis pipeline = THE BLEND (video/scripts/blend_voice_previews.py): Gemini TTS supplies calm,
conversational human DELIVERY (prosody/pacing), then ElevenLabs Speech-to-Speech re-voices it into
the brand voice below — identity unchanged, robotic cadence gone. Live calls reuse the same chain
for non-realtime lines (greetings, confirmations); realtime turns use the ElevenLabs voice directly
with the validated settings (stability 0.4 / similarity 0.85 — never 0.2/style-0.6, the documented
robotic trap).
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_VOICE = "riley"


@dataclass(frozen=True)
class Voice:
    key: str
    label: str
    description: str
    elevenlabs_voice_id: str  # premade ElevenLabs voice powering live calls + the preview


VOICES: dict[str, Voice] = {
    v.key: v
    for v in (
        Voice(
            "riley", "Riley",
            "Warm and personable — sounds like your best CSR on a good morning.",
            elevenlabs_voice_id="hpp4J3VqNfWAUOO0d1Us",  # "Bella — Professional, Bright, Warm"
        ),
        Voice(
            "marcus", "Marcus",
            "Calm, seasoned, and reassuring — the steady voice for service calls.",
            elevenlabs_voice_id="nPczCjzI2devNBz1zQrb",  # "Brian — Deep, Resonant and Comforting"
        ),
        Voice(
            "jade", "Jade",
            "Bright and upbeat — keeps even the 2 a.m. callers at ease.",
            elevenlabs_voice_id="tnSpp4vdxKPjI9w0GnoV",  # "Hope — upbeat and clear"
        ),
    )
}


def get_voice(key: str) -> Voice | None:
    return VOICES.get((key or "").strip().lower())


def is_valid(key: str) -> bool:
    return get_voice(key) is not None


def as_list() -> list[dict]:
    return [
        {
            "key": v.key,
            "label": v.label,
            "description": v.description,
            "preview_url": f"/voices/{v.key}.mp3",
        }
        for v in VOICES.values()
    ]
