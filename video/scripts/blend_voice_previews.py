"""Blend-upgrade the booking-agent voice previews (frontend/public/voices/*.mp3).

THE BLEND (validated in the cory-voice skill): Gemini TTS supplies the human conversational
DELIVERY (prosody, pacing, calm), then ElevenLabs Speech-to-Speech re-voices it into the brand
ElevenLabs voice (timbre/identity unchanged from app/voice/voices.py). Result: the same Riley/
Marcus/Jade the picker advertises, with enterprise-calm, non-robotic delivery. The live telephony
layer uses the same chain for non-realtime lines (greeting, confirmations).

Keys read at runtime (never hardcoded): ELEVENLABS_API_KEY <- LCE .env, GEMINI_API_KEY <- Content
Engine .env. STS settings are the skill-validated ones — do NOT ship stability 0.2 + style 0.6
(the documented robotic trap).
"""
from __future__ import annotations

import base64
import json
import pathlib
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import wave

LCE_ENV = pathlib.Path(r"C:\Users\you\Downloads\Local Content Engine - LLM Native\.env")
GEM_ENV = pathlib.Path(r"C:\Users\you\Downloads\Content Engine\.env")
OUT_DIR = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "public" / "voices"

GEMINI_MODEL = "gemini-3.1-flash-tts-preview"
STS_MODEL = "eleven_multilingual_sts_v2"
STS_SETTINGS = {"stability": 0.4, "similarity_boost": 0.85, "style": 0.0, "use_speaker_boost": True}
EL_FMT = "mp3_44100_192"

STYLE = (
    "Read as a calm, warm, highly professional customer-service agent on a live phone call — "
    "natural pauses, unhurried, reassuring, genuinely conversational, never salesy:"
)

# key -> (elevenlabs target id [MUST match app/voice/voices.py], gemini flow voice, sample script)
VOICES = {
    "riley": (
        "hpp4J3VqNfWAUOO0d1Us",  # Bella — the brand timbre
        "Sulafat",               # warm Gemini delivery
        "Thanks for calling Canyon Ridge Mechanical — this is Riley. … Of course. No heat "
        "overnight is miserable, so let's get that handled right now. I have a technician in "
        "your area tomorrow between nine and eleven… I'll book it, and you'll have a "
        "confirmation text before we hang up.",
    ),
    "marcus": (
        "nPczCjzI2devNBz1zQrb",  # Brian
        "Charon",                # the validated calm male flow
        "Thanks for calling Canyon Ridge Mechanical, this is Marcus. … I understand — a leak "
        "like that can't wait. The closest technician wraps up about forty minutes from you… "
        "I'm scheduling him now, and I'll text you his arrival window right away.",
    ),
    "jade": (
        "tnSpp4vdxKPjI9w0GnoV",  # Hope
        "Aoede",                 # bright but easy Gemini delivery
        "You've reached Canyon Ridge Mechanical — this is Jade. … Absolutely, even at two in "
        "the morning, we pick up. Let me grab your address and get the right tech assigned… "
        "and you'll have the confirmation in your messages before we're done.",
    ),
}


def _env_val(path: pathlib.Path, key: str) -> str:
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if s.startswith(key + "="):
            return s.split("=", 1)[1].strip().strip('"').strip("'")
    raise KeyError(f"{key} not found in {path}")


EL_KEY = _env_val(LCE_ENV, "ELEVENLABS_API_KEY")
GEM_KEY = _env_val(GEM_ENV, "GEMINI_API_KEY")


def _read_url(req: urllib.request.Request, timeout: int = 180, retries: int = 3) -> bytes:
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code < 500:
                sys.stderr.write(f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}\n")
                raise
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def gemini_tts(text: str, voice: str, out: pathlib.Path) -> None:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEM_KEY}"
    body = json.dumps({
        "contents": [{"parts": [{"text": f"{STYLE} {text}"}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    d = json.loads(_read_url(req))
    part = d["candidates"][0]["content"]["parts"][0]["inlineData"]
    pcm = base64.b64decode(part["data"])
    rate = 24000
    if "rate=" in part.get("mimeType", ""):
        try:
            rate = int(part["mimeType"].split("rate=")[1].split(";")[0])
        except Exception:
            pass
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


def el_sts(src: pathlib.Path, out: pathlib.Path, voice_id: str) -> None:
    boundary = uuid.uuid4().hex
    buf = bytearray()
    for k, v in {"model_id": STS_MODEL, "voice_settings": json.dumps(STS_SETTINGS)}.items():
        buf += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    buf += (f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="{src.name}"\r\n'
            "Content-Type: audio/wav\r\n\r\n").encode() + src.read_bytes() + b"\r\n"
    buf += f"--{boundary}--\r\n".encode()
    url = f"https://api.elevenlabs.io/v1/speech-to-speech/{voice_id}?output_format={EL_FMT}"
    req = urllib.request.Request(url, data=bytes(buf), method="POST", headers={
        "xi-api-key": EL_KEY, "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "audio/mpeg",
    })
    out.write_bytes(_read_url(req))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for key, (el_id, gem_voice, text) in VOICES.items():
        tmp = pathlib.Path(tempfile.gettempdir()) / f"_flow_{uuid.uuid4().hex}.wav"
        try:
            gemini_tts(text, gem_voice, tmp)
            out = OUT_DIR / f"{key}.mp3"
            el_sts(tmp, out, el_id)
            print(f"{key}: {gem_voice} flow -> STS {el_id} -> {out} ({out.stat().st_size:,} bytes)")
        finally:
            tmp.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
