"""Voice bake-off: generate a small test set across candidate TTS configs, score each with UTMOS,
and test the 'humanize' post-processing chain on the top configs. Picks the most human-sounding config
objectively (no listening required) so add_voiceover.py can adopt the winner.

Providers: ElevenLabs (the user's cloned voice, multiple models/settings) + Google Gemini native TTS
(stock voice, for reference — can't clone the user's voice). Scored with UTMOS (score_mos.py).

Run:  python scripts/voice_bakeoff.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import score_mos  # noqa: E402  (UTMOS scorer)

VIDEO_DIR = pathlib.Path(__file__).resolve().parents[1]
BAKE = VIDEO_DIR / "bakeoff"
BAKE.mkdir(exist_ok=True)
LCE_ENV = pathlib.Path("C:/Users/you/Downloads/Local Content Engine - LLM Native/.env")
GEM_ENV = pathlib.Path("C:/Users/you/Downloads/Content Engine/.env")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _env_val(path: pathlib.Path, key: str) -> str:
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if s.startswith(key + "="):
            return s.split("=", 1)[1].strip().strip('"').strip("'")
    raise KeyError(key)


EL_KEY = _env_val(LCE_ENV, "ELEVENLABS_API_KEY")
GEM_KEY = _env_val(GEM_ENV, "GEMINI_API_KEY")

VOICES = {"cory_new": "REDACTED_ID", "cory_orig": "REDACTED_ID"}

# 3 representative lines: multi-sentence open, a number/currency line, the brand+acronym CTA.
TEST_LINES = [
    "Two fourteen in the morning. Nobody's awake. Your agents are.",
    "Your phones never sleep. Two thousand, eight hundred, ninety-five dollars recovered, after hours.",
    "Top Builder AI, the operating layer for ServiceTitan. Top builder A I dot com.",
]

# Candidate configs.
CONFIGS = [
    {"name": "EL_baseline_0.20_style0.60_128", "provider": "el", "voice": "cory_new", "model": "eleven_multilingual_v2",
     "settings": {"stability": 0.20, "similarity_boost": 0.80, "style": 0.60, "use_speaker_boost": True}, "fmt": "mp3_44100_128"},
    {"name": "EL_fix_0.45_192", "provider": "el", "voice": "cory_new", "model": "eleven_multilingual_v2",
     "settings": {"stability": 0.45, "similarity_boost": 0.78, "style": 0.0, "use_speaker_boost": True}, "fmt": "mp3_44100_192"},
    {"name": "EL_0.40_192", "provider": "el", "voice": "cory_new", "model": "eleven_multilingual_v2",
     "settings": {"stability": 0.40, "similarity_boost": 0.78, "style": 0.0, "use_speaker_boost": True}, "fmt": "mp3_44100_192"},
    {"name": "EL_0.55_192", "provider": "el", "voice": "cory_new", "model": "eleven_multilingual_v2",
     "settings": {"stability": 0.55, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True}, "fmt": "mp3_44100_192"},
    {"name": "EL_origVoice_0.45_192", "provider": "el", "voice": "cory_orig", "model": "eleven_multilingual_v2",
     "settings": {"stability": 0.45, "similarity_boost": 0.78, "style": 0.0, "use_speaker_boost": True}, "fmt": "mp3_44100_192"},
    {"name": "EL_v3_natural", "provider": "el", "voice": "cory_new", "model": "eleven_v3",
     "settings": {"stability": 0.5, "similarity_boost": 0.75}, "fmt": "mp3_44100_192"},
    {"name": "Gemini31_Charon", "provider": "gemini", "model": "gemini-3.1-flash-tts-preview", "gem_voice": "Charon",
     "style": "Read in a warm, confident, conversational male voice, like a friendly expert narrator:"},
    {"name": "EL_0.60_192", "provider": "el", "voice": "cory_new", "model": "eleven_multilingual_v2",
     "settings": {"stability": 0.60, "similarity_boost": 0.78, "style": 0.0, "use_speaker_boost": True}, "fmt": "mp3_44100_192"},
    {"name": "EL_0.65_192", "provider": "el", "voice": "cory_new", "model": "eleven_multilingual_v2",
     "settings": {"stability": 0.65, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True}, "fmt": "mp3_44100_192"},
    {"name": "EL_origVoice_0.55_192", "provider": "el", "voice": "cory_orig", "model": "eleven_multilingual_v2",
     "settings": {"stability": 0.55, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True}, "fmt": "mp3_44100_192"},
    {"name": "Gemini31_Orus", "provider": "gemini", "model": "gemini-3.1-flash-tts-preview", "gem_voice": "Orus",
     "style": "Read in a warm, confident, conversational male voice, like a friendly expert narrator:"},
    {"name": "Gemini31_Iapetus", "provider": "gemini", "model": "gemini-3.1-flash-tts-preview", "gem_voice": "Iapetus",
     "style": "Read in a warm, confident, conversational male voice, like a friendly expert narrator:"},
]


def el_tts(text: str, voice_id: str, model: str, settings: dict, fmt: str, out: pathlib.Path) -> None:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format={fmt}"
    body = json.dumps({"text": text, "model_id": model, "voice_settings": settings,
                       "apply_text_normalization": "auto"}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"xi-api-key": EL_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    with urllib.request.urlopen(req, timeout=120) as r:
        out.write_bytes(r.read())


def gemini_tts(text: str, model: str, voice: str, style: str, out: pathlib.Path) -> None:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEM_KEY}"
    body = json.dumps({
        "contents": [{"parts": [{"text": f"{style} {text}"}]}],
        "generationConfig": {"responseModalities": ["AUDIO"],
                             "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}},
    }).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    part = d["candidates"][0]["content"]["parts"][0]["inlineData"]
    pcm = __import__("base64").b64decode(part["data"])
    rate = 24000
    mime = part.get("mimeType", "")
    if "rate=" in mime:
        try:
            rate = int(mime.split("rate=")[1].split(";")[0])
        except Exception:
            pass
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


def gen(cfg: dict, idx: int, text: str) -> pathlib.Path | None:
    ext = "wav" if cfg["provider"] == "gemini" else "mp3"
    out = BAKE / f"{cfg['name']}__{idx}.{ext}"
    if out.exists() and out.stat().st_size > 2000:
        return out
    try:
        if cfg["provider"] == "el":
            el_tts(text, VOICES[cfg["voice"]], cfg["model"], cfg["settings"], cfg["fmt"], out)
        else:
            gemini_tts(text, cfg["model"], cfg["gem_voice"], cfg["style"], out)
        return out
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"  {cfg['name']}[{idx}] HTTP {e.code}: {e.read().decode('utf-8','ignore')[:200]}\n")
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"  {cfg['name']}[{idx}] ERR {type(e).__name__}: {str(e)[:200]}\n")
    return None


def humanize(src: pathlib.Path, dst: pathlib.Path) -> bool:
    """Two-pass 'humanize' chain: de-ess, presence EQ, gentle compression, exciter, subtle room tone, -16 LUFS."""
    p1 = subprocess.run(["ffmpeg", "-y", "-i", str(src), "-af",
                         "loudnorm=I=-16:TP=-1.0:LRA=11:print_format=json", "-f", "null", "-"],
                        capture_output=True, text=True)
    try:
        txt = p1.stderr
        blob = txt[txt.rindex("{"):txt.rindex("}") + 1]
        m = json.loads(blob)
        mi, mtp, mlra, mth = m["input_i"], m["input_tp"], m["input_lra"], m["input_thresh"]
    except Exception:
        mi, mtp, mlra, mth = "-24", "-2", "7", "-34"
    chain = (
        "deesser=i=0.4:m=0.5:f=0.18:s=o,"
        "equalizer=f=180:t=q:w=1.0:g=-2,"
        "equalizer=f=3200:t=q:w=1.4:g=3,"
        "equalizer=f=10000:t=q:w=1.2:g=2,"
        "acompressor=threshold=-18dB:ratio=2.8:attack=15:release=180:knee=4:makeup=2,"
        "aexciter=amount=1.2:drive=6:freq=7500,"
        "aecho=in_gain=0.9:out_gain=0.22:delays=23|37:decays=0.18|0.12,"
        f"loudnorm=I=-16:TP=-1.0:LRA=11:measured_I={mi}:measured_TP={mtp}:measured_LRA={mlra}:measured_thresh={mth}:linear=true,"
        "alimiter=limit=0.89"  # linear ~= -1 dBTP (alimiter limit is 0.0625-1.0, NOT dB)
    )
    r = subprocess.run(["ffmpeg", "-y", "-i", str(src), "-af", chain, "-c:a", "libmp3lame", "-b:a", "192k", str(dst)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write("  humanize FAILED: " + r.stderr[-400:] + "\n")
        return False
    return True


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


if __name__ == "__main__":
    print(f"Bake-off: {len(CONFIGS)} configs x {len(TEST_LINES)} lines\n")
    rows = []
    for cfg in CONFIGS:
        scores = []
        for idx, line in enumerate(TEST_LINES):
            clip = gen(cfg, idx, line)
            if clip:
                try:
                    scores.append(score_mos.score(clip))
                except Exception as e:  # noqa: BLE001
                    sys.stderr.write(f"  score err {cfg['name']}[{idx}]: {str(e)[:120]}\n")
        m = mean(scores)
        rows.append((m, cfg["name"], scores))
        print(f"  {m:5.3f}  {cfg['name']:34}  {[round(s,2) for s in scores]}")

    rows.sort(reverse=True)
    print("\n=== RANKED (dry UTMOS, mean of 3 lines) ===")
    for m, name, _ in rows:
        print(f"  {m:5.3f}  {name}")

    # Humanize the top-2 ElevenLabs configs + baseline, re-score.
    print("\n=== HUMANIZE post-chain (top EL configs) ===")
    to_process = rows[:3] + [r for r in rows if "baseline" in r[1]]
    seen = set()
    for m, name, _ in to_process:
        if name in seen:
            continue
        seen.add(name)
        proc_scores = []
        for idx in range(len(TEST_LINES)):
            src = next(BAKE.glob(f"{name}__{idx}.*"), None)
            if not src:
                continue
            dst = BAKE / f"{name}__{idx}__hp.mp3"
            if humanize(src, dst):
                try:
                    proc_scores.append(score_mos.score(dst))
                except Exception:
                    pass
        if proc_scores:
            pm = mean(proc_scores)
            print(f"  {pm:5.3f}  {name} + humanize   (dry was {m:.3f}, delta {pm - m:+.3f})")
    print("\nDONE — pick the highest mean; >=4.0 = human-grade.")
