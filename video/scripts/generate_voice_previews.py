"""Generate the 3 booking-agent phone-voice previews (frontend/public/voices/*.mp3).

Reads ELEVENLABS_API_KEY from the Local Content Engine .env (never hardcoded/printed). Each preview
is the actual ElevenLabs premade voice the live telephony layer will use (`app/voice/voices.py`),
speaking a phone greeting — so the picker plays exactly what callers will hear. Settings follow the
validated cory-voice recipe for clean v2 output (stability 0.5 / similarity 0.75).
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ENV_PATH = Path(r"C:\Users\you\Downloads\Local Content Engine - LLM Native\.env")
OUT_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "voices"

VOICES = {
    # key -> (elevenlabs_voice_id, greeting) — ids must match backend/app/voice/voices.py
    "riley": (
        "hpp4J3VqNfWAUOO0d1Us",
        "Thanks for calling Canyon Ridge Mechanical! This is Riley. Are you calling about a "
        "repair, or to get something scheduled? I can book you in right now.",
    ),
    "marcus": (
        "nPczCjzI2devNBz1zQrb",
        "Thanks for calling Canyon Ridge Mechanical — this is Marcus. Tell me what's going on "
        "with your system, and I'll get a technician headed your way.",
    ),
    "jade": (
        "tnSpp4vdxKPjI9w0GnoV",
        "Hi, you've reached Canyon Ridge Mechanical — this is Jade! Even at two in the morning, "
        "we've got you covered. What can I help with?",
    ),
}


def read_key() -> str:
    for line in ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip().startswith("ELEVENLABS_API_KEY"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("ELEVENLABS_API_KEY not found in the LCE .env")


def main() -> int:
    key = read_key()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Sanity-check the premade voice ids actually exist on this account's library.
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        available = {v["voice_id"]: v["name"] for v in json.loads(resp.read())["voices"]}

    for voice_key, (voice_id, text) in VOICES.items():
        label = available.get(voice_id, "NOT IN LIBRARY")
        print(f"{voice_key}: voice_id={voice_id} ({label})")
        body = json.dumps(
            {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            }
        ).encode()
        r = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
            data=body,
            headers={"xi-api-key": key, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(r, timeout=120) as resp:
            audio = resp.read()
        out = OUT_DIR / f"{voice_key}.mp3"
        out.write_bytes(audio)
        print(f"  -> {out} ({len(audio):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
