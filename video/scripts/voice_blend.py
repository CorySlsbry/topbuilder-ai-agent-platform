"""Blend = Gemini Charon's flow/cadence + Cory's voice (timbre), via ElevenLabs Speech-to-Speech.

STS ("Voice Changer") takes a SOURCE audio (delivery/timing/flow we like = Charon) and re-renders it in a
TARGET voice (Cory's clone), preserving the source's cadence. So: Gemini Charon narration -> STS to Cory.

This prototype STS-converts the 3 existing Charon bake-off clips and writes an audition sample to Downloads.
Run:  python scripts/voice_blend.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import score_mos  # noqa: E402

VIDEO_DIR = pathlib.Path(__file__).resolve().parents[1]
BAKE = VIDEO_DIR / "bakeoff"
DOWNLOADS = pathlib.Path("C:/Users/you/Downloads")
LCE_ENV = pathlib.Path("C:/Users/you/Downloads/Local Content Engine - LLM Native/.env")

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
CORY_VOICE = "REDACTED_ID"
STS_MODEL = "eleven_multilingual_sts_v2"
STS_SETTINGS = {"stability": 0.4, "similarity_boost": 0.85, "style": 0.0, "use_speaker_boost": True}


def _multipart(fields: dict, file_field: str, file_path: pathlib.Path, file_mime: str) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    buf = bytearray()
    for k, v in fields.items():
        buf += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    buf += (f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
            f'filename="{file_path.name}"\r\nContent-Type: {file_mime}\r\n\r\n').encode()
    buf += file_path.read_bytes()
    buf += f"\r\n--{boundary}--\r\n".encode()
    return bytes(buf), boundary


def el_sts(src: pathlib.Path, voice_id: str, out: pathlib.Path,
           model: str = STS_MODEL, fmt: str = "mp3_44100_192", settings: dict | None = None) -> None:
    fields = {"model_id": model}
    if settings:
        fields["voice_settings"] = json.dumps(settings)
    mime = "audio/wav" if src.suffix.lower() == ".wav" else "audio/mpeg"
    body, boundary = _multipart(fields, "audio", src, mime)
    url = f"https://api.elevenlabs.io/v1/speech-to-speech/{voice_id}?output_format={fmt}"
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "xi-api-key": EL_KEY, "Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "audio/mpeg"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            out.write_bytes(r.read())
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"STS HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:400]}\n")
        raise


def concat_sample(clips: list[pathlib.Path], out: pathlib.Path) -> None:
    inputs: list[str] = []
    for c in clips:
        inputs += ["-i", str(c)]
    parts = []
    for j in range(len(clips)):
        af = "[%d:a]aformat=sample_rates=44100:channel_layouts=mono" % j
        if j < len(clips) - 1:
            af += ",apad=pad_dur=0.55"
        parts.append(af + f"[p{j}]")
    filt = ";".join(parts) + ";" + "".join(f"[p{j}]" for j in range(len(clips))) + \
        f"concat=n={len(clips)}:v=0:a=1,loudnorm=I=-16:TP=-1.5:LRA=11[out]"
    subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex", filt, "-map", "[out]",
                    "-c:a", "libmp3lame", "-b:a", "192k", str(out)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


STS_CONFIGS = [
    ("ml_sim85_stab40", "eleven_multilingual_sts_v2", {"stability": 0.4, "similarity_boost": 0.85, "style": 0.0, "use_speaker_boost": True}),
    ("ml_sim90_stab50", "eleven_multilingual_sts_v2", {"stability": 0.5, "similarity_boost": 0.90, "style": 0.0, "use_speaker_boost": True}),
    ("ml_sim80_stab30", "eleven_multilingual_sts_v2", {"stability": 0.3, "similarity_boost": 0.80, "style": 0.0, "use_speaker_boost": True}),
    ("en_sim85_stab50", "eleven_english_sts_v2", {"stability": 0.5, "similarity_boost": 0.85, "style": 0.0, "use_speaker_boost": True}),
    ("en_sim90_stab40", "eleven_english_sts_v2", {"stability": 0.4, "similarity_boost": 0.90, "style": 0.0, "use_speaker_boost": True}),
]

if __name__ == "__main__":
    srcs = [BAKE / f"Gemini31_Charon__{i}.wav" for i in range(3)]
    print(f"STS blend sweep: Charon source -> Cory voice {CORY_VOICE}\n")
    results = []
    for cname, model, settings in STS_CONFIGS:
        clips, scores = [], []
        for i, src in enumerate(srcs):
            out = BAKE / f"blend_{cname}_{i}.mp3"
            if not (out.exists() and out.stat().st_size > 2000):
                try:
                    el_sts(src, CORY_VOICE, out, model=model, settings=settings)
                except Exception as e:  # noqa: BLE001
                    sys.stderr.write(f"  {cname}[{i}] {type(e).__name__}: {str(e)[:120]}\n")
                    continue
            clips.append(out)
            scores.append(score_mos.score(out))
        m = sum(scores) / len(scores) if scores else 0.0
        results.append((m, cname, clips))
        print(f"  {m:5.3f}  {cname:18}  {[round(s, 2) for s in scores]}")
    results.sort(reverse=True)
    best_m, best_name, best_clips = results[0]
    print(f"\nBEST STS config: {best_name}  (mean UTMOS {best_m:.3f})")
    if best_clips:
        sample = DOWNLOADS / "VOICE-E-blend.mp3"
        concat_sample(best_clips, sample)
        print(f"WROTE {sample}")
