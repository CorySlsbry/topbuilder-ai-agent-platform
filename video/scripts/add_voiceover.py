"""Expressive ElevenLabs voiceover (Cory's cloned voice) + video-follows-voice timing.

Pipeline (one atomic run):
  1. Generate/measure a per-scene narration clip for each composition (cached as *_v2_*.mp3).
  2. Compute each scene's duration from its clip length  ->  write src/voTiming.ts.
  3. Re-render both Remotion compositions so every scene lasts exactly its narration line.
  4. Mux each clip onto its scene (start = scene_start + LEAD)  ->  no overlap, no drift, perfect sync.
  5. Re-encode to a universally compatible MP4 (yuv420p + faststart) and copy to Downloads.

Voice tuning that fixed "robotic + talks over itself":
  - model eleven_multilingual_v2 (more expressive than turbo for a cloned voice)
  - low stability + higher style = energy/excitement; high similarity keeps it Cory
  - deterministic 1s silence between sentences  ->  a "stop" ONLY after each period (per-sentence TTS + apad concat)
  - the picture follows the voice (no fixed scene clock), so lines never collide

The ElevenLabs key is read from the Local Content Engine `.env` (no secret stored here).
Run:  python video/scripts/add_voiceover.py
"""
from __future__ import annotations

import base64
import json
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import wave

VIDEO_DIR = pathlib.Path(__file__).resolve().parents[1]
OUT = VIDEO_DIR / "out"
VO = VIDEO_DIR / "vo"
TIMING_TS = VIDEO_DIR / "src" / "voTiming.ts"
VO.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)
DOWNLOADS = pathlib.Path("C:/Users/you/Downloads")
LCE_ENV = pathlib.Path("C:/Users/you/Downloads/Local Content Engine - LLM Native/.env")

try:  # Windows cp1252 console can't encode some glyphs; force UTF-8 so prints never crash the run
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FPS = 30
LEAD = 0.5   # scene fades in, then the line starts
TAIL = 0.7   # the line ends, brief hold, then cross-fade to the next scene
MODEL = "eleven_v3"                        # ElevenLabs' most human model — chosen via UTMOS bake-off + ear test
# v3 takes ONLY stability + similarity_boost (style/use_speaker_boost are ignored). ~0.5 = the "Natural" preset.
SETTINGS = {"stability": 0.5, "similarity_boost": 0.75}
CLIP_VER = "v6"                            # bump to bust the on-disk clip cache when SETTINGS/voice/model change
V3_TAKES = 2                               # v3 is non-deterministic: N takes per line, keep the best by UTMOS
OUTPUT_FORMAT = "mp3_44100_192"            # 192 kbps (vs default 128) for fidelity

# Production voice = the BLEND (Cory's ear pick): Gemini Charon's flow re-voiced into Cory's clone via
# ElevenLabs Speech-to-Speech. The narration below is written in smooth, connected phrasing for flow.
SYNTH_MODE = "blend"                       # "blend" (Charon -> STS -> Cory) | "v3" | "v2"
BLEND_TAKES = 2                            # takes per line (Gemini + STS), keep the best by UTMOS
GEM_ENV = pathlib.Path("C:/Users/you/Downloads/Content Engine/.env")
CHARON_MODEL = "gemini-3.1-flash-tts-preview"
CHARON_VOICE = "Charon"
CHARON_STYLE = "Read in a warm, confident, conversational male voice, like a friendly expert narrator:"
STS_MODEL = "eleven_multilingual_sts_v2"
STS_SETTINGS = {"stability": 0.4, "similarity_boost": 0.85, "style": 0.0, "use_speaker_boost": True}


def load_env(path: pathlib.Path) -> dict:
    env = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


_env = load_env(LCE_ENV)
KEY = _env["ELEVENLABS_API_KEY"]
GEM_KEY = load_env(GEM_ENV)["GEMINI_API_KEY"]
# Locked voice — UTMOS bake-off + Cory's ear pick (the blend: Charon flow -> Cory's clone via STS).
VOICE = "REDACTED_ID"
print(f"synth_mode={SYNTH_MODE} voice={VOICE} (blend: {CHARON_VOICE} -> STS {STS_MODEL})")


PAUSE = 1.0  # seconds of silence inserted AFTER each period (between sentences) — the only "stops"


def split_sentences(text: str) -> list[str]:
    # Split on whitespace that follows a sentence-ending . ! ? — each piece keeps its terminator.
    return [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p]


def _read_url(req: urllib.request.Request, timeout: int, tries: int = 4) -> bytes:
    """POST/GET with retry + backoff on timeouts and transient (429/5xx) errors — long STS/TTS reads flake
    on the network leg, and a half-finished batch shouldn't kill the whole render."""
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            sys.stderr.write(f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}\n")
            raise
        except (TimeoutError, ConnectionError, urllib.error.URLError) as e:
            if attempt < tries - 1:
                sys.stderr.write(f"  retry {attempt + 1}/{tries} after {type(e).__name__}\n")
                time.sleep(2 * (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


def tts(text: str, path: pathlib.Path) -> None:
    # One clean TTS call, NO break tags — the deliberate stops are added as real silence (see synth_scene).
    body = json.dumps({"text": text, "model_id": MODEL, "voice_settings": SETTINGS}).encode("utf-8")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}?output_format={OUTPUT_FORMAT}"
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"xi-api-key": KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    path.write_bytes(_read_url(req, 120))


def _utmos_pick(cands: list[pathlib.Path]) -> pathlib.Path:
    """Return the most natural candidate by UTMOS (falls back to take 0 if scoring is unavailable)."""
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import score_mos  # noqa: PLC0415
        scored = sorted(((score_mos.score(c), c) for c in cands), key=lambda x: x[0], reverse=True)
        print("    v3 takes UTMOS: " + str([round(s, 2) for s, _ in scored]))
        return scored[0][1]
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"    UTMOS pick skipped ({type(e).__name__}: {str(e)[:80]}); using take 0\n")
        return cands[0]


def synth_v3_line(text: str, clip: pathlib.Path) -> None:
    """eleven_v3 path: synthesize the WHOLE line (v3 reads multi-sentence prompts naturally and handles its
    own pauses), generate V3_TAKES non-deterministic takes, and keep the most natural one by UTMOS."""
    cands: list[pathlib.Path] = []
    for t in range(max(1, V3_TAKES)):
        c = clip.with_name(f"{clip.stem}.take{t}.mp3")
        tts(text, c)
        cands.append(c)
    best = _utmos_pick(cands) if len(cands) > 1 else cands[0]
    shutil.copy(best, clip)
    for c in cands:
        try:
            c.unlink()
        except Exception:
            pass


def gemini_charon(text: str, out_wav: pathlib.Path) -> None:
    """Gemini native TTS (Charon voice) — the 'flow' source for the blend."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{CHARON_MODEL}:generateContent?key={GEM_KEY}"
    body = json.dumps({
        "contents": [{"parts": [{"text": f"{CHARON_STYLE} {text}"}]}],
        "generationConfig": {"responseModalities": ["AUDIO"],
                             "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": CHARON_VOICE}}}},
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    d = json.loads(_read_url(req, 120))
    part = d["candidates"][0]["content"]["parts"][0]["inlineData"]
    pcm = base64.b64decode(part["data"])
    rate = 24000
    if "rate=" in part.get("mimeType", ""):
        try:
            rate = int(part["mimeType"].split("rate=")[1].split(";")[0])
        except Exception:
            pass
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


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


def el_sts(src: pathlib.Path, out: pathlib.Path) -> None:
    """ElevenLabs Speech-to-Speech: re-voice the Charon source into Cory's clone (keeps the source's flow)."""
    fields = {"model_id": STS_MODEL, "voice_settings": json.dumps(STS_SETTINGS)}
    mime = "audio/wav" if src.suffix.lower() == ".wav" else "audio/mpeg"
    body, boundary = _multipart(fields, "audio", src, mime)
    url = f"https://api.elevenlabs.io/v1/speech-to-speech/{VOICE}?output_format={OUTPUT_FORMAT}"
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "xi-api-key": KEY, "Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "audio/mpeg"})
    out.write_bytes(_read_url(req, 300))


def synth_blend(text: str, clip: pathlib.Path) -> None:
    """Blend path: Gemini Charon (flow) -> ElevenLabs STS into Cory's voice (timbre). N takes, best by UTMOS."""
    cands: list[pathlib.Path] = []
    for t in range(max(1, BLEND_TAKES)):
        src = clip.with_name(f"{clip.stem}.charon{t}.wav")
        cand = clip.with_name(f"{clip.stem}.take{t}.mp3")
        gemini_charon(text, src)
        el_sts(src, cand)
        cands.append(cand)
        try:
            src.unlink()
        except Exception:
            pass
    best = _utmos_pick(cands) if len(cands) > 1 else cands[0]
    shutil.copy(best, clip)
    for c in cands:
        try:
            c.unlink()
        except Exception:
            pass


def synth_scene(text: str, clip: pathlib.Path) -> None:
    """One narration line -> one MP3. blend = Charon -> STS -> Cory; eleven_v3 reads the whole line;
    multilingual_v2 splits into sentences with deterministic silence between them.
    """
    if SYNTH_MODE == "blend":
        synth_blend(text, clip)
        return
    if MODEL.startswith("eleven_v3"):
        synth_v3_line(text, clip)
        return
    sents = split_sentences(text)
    if len(sents) <= 1:
        tts(text, clip)
        return
    temps: list[pathlib.Path] = []
    for j, s in enumerate(sents):
        tp = VO / f".tmp_{clip.stem}_{j}.mp3"
        tts(s, tp)
        temps.append(tp)
    inputs: list[str] = []
    for tp in temps:
        inputs += ["-i", str(tp)]
    parts = []
    for j in range(len(temps)):
        af = f"[{j}:a]aformat=sample_rates=44100:channel_layouts=stereo"
        if j < len(temps) - 1:
            af += f",apad=pad_dur={PAUSE}"
        parts.append(af + f"[p{j}]")
    concat = "".join(f"[p{j}]" for j in range(len(temps))) + f"concat=n={len(temps)}:v=0:a=1[out]"
    filt = ";".join(parts) + ";" + concat
    subprocess.run(
        ["ffmpeg", "-y", *inputs, "-filter_complex", filt, "-map", "[out]",
         "-c:a", "libmp3lame", "-b:a", "192k", str(clip)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for tp in temps:
        tp.unlink()


def ffprobe_dur(path: pathlib.Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def ensure_clips(name: str, lines: list[str]) -> tuple[list[pathlib.Path], list[float]]:
    paths, durs = [], []
    for idx, text in enumerate(lines):
        clip = VO / f"{name}_{CLIP_VER}_{idx:02d}.mp3"
        if not (clip.exists() and clip.stat().st_size > 2000):
            print(f"  tts {name}[{idx}]: {text[:60]}")
            synth_scene(text, clip)
        paths.append(clip)
        durs.append(ffprobe_dur(clip))
    return paths, durs


def scene_frames(clip_durs: list[float]) -> list[int]:
    return [round((LEAD + d + TAIL) * FPS) for d in clip_durs]


def write_timing(timings: dict[str, list[int]]) -> None:
    arrs = ",\n".join(f"  {k}: {json.dumps(v)}" for k, v in timings.items())
    type_fields = "; ".join(f"{k}: number[]" for k in timings)
    TIMING_TS.write_text(
        "// AUTO-GENERATED by scripts/add_voiceover.py — per-scene durations in frames (30fps), sized so each\n"
        "// scene lasts exactly its narration line (video-follows-voice). Regenerated on every voiceover run.\n"
        "// null => the compositions fall back to their hand-authored default timing.\n"
        f"export type VoTiming = {{ {type_fields} }};\n"
        f"export const VO_TIMING: VoTiming | null = {{\n{arrs},\n}};\n",
        encoding="utf-8",
    )
    print(f"  wrote {TIMING_TS.relative_to(VIDEO_DIR)}  ->  {timings}")


def render(npm_script: str) -> None:
    print(f"  rendering: npm run {npm_script} ...")
    r = subprocess.run(
        f"npm run {npm_script}", cwd=str(VIDEO_DIR), shell=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    if r.returncode != 0:
        sys.stderr.write((r.stderr or "")[-3000:] + "\n")
        raise RuntimeError(f"render failed: {npm_script}")


def mux(base_mp4: pathlib.Path, paths: list[pathlib.Path], clip_durs: list[float],
        frame_durs: list[int], downloads_path: pathlib.Path) -> None:
    # Scene start (frames) = cumulative prior scene durations; the line starts LEAD after that.
    start_frames, acc = [], 0
    for d in frame_durs:
        start_frames.append(acc)
        acc += d
    clip_starts = [sf / FPS + LEAD for sf in start_frames]

    video_dur = ffprobe_dur(base_mp4)
    vo_end = clip_starts[-1] + clip_durs[-1]
    for i, (cs, cd) in enumerate(zip(clip_starts, clip_durs)):
        print(f"  [{i:02d}] line @ {cs:>5.1f}s  dur {cd:>4.1f}s  scene {frame_durs[i] / FPS:>4.1f}s")
    print(f"  vo_end {vo_end:.1f}s  video {video_dur:.1f}s  (line ends {video_dur - vo_end:.1f}s before the cut)")

    inputs: list[str] = []
    for p in paths:
        inputs += ["-i", str(p)]
    aparts = [
        f"[{i + 1}]adelay={int(clip_starts[i] * 1000)}:all=1,aformat=sample_rates=44100:channel_layouts=stereo[a{i}]"
        for i in range(len(paths))
    ]
    amix = "".join(f"[a{i}]" for i in range(len(paths))) + f"amix=inputs={len(paths)}:normalize=0:dropout_transition=0[vo]"
    filt = ";".join(aparts) + ";" + amix

    out_vo = OUT / f"{base_mp4.stem}-vo.mp4"
    cmd = [
        "ffmpeg", "-y", "-i", str(base_mp4), *inputs, "-filter_complex", filt,
        "-map", "0:v", "-map", "[vo]",
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
        "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k", str(out_vo),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.copy(out_vo, downloads_path)
    print(f"  WROTE {out_vo.name}  ->  {downloads_path}")


# Tight 1-2 sentence narration per scene; the picture stretches to fit each line.
EXPLAINER = [
    "It's two fourteen in the morning, a call comes in, and it's the kind most shops would miss.",
    "Top Builder AI reeds ServiceTitan, reed only, so your data is never touched.",
    "All of the numbers come from tested code, and the model only writes the words.",
    "It proposes the booking and then stops at the gate, so nothing is written yet.",
    "You approve it, and only then does the gate open.",
    "Now it writes back to ServiceTitan, signed, logged, and reversible, and if it isn't verified, it just refuses.",
    "All six agents run that same loop, they reed, they propose, they approve, and they write.",
    "And every edit you make teaches them, so they sound more like your shop every week.",
    "Top Builder AI, the operating layer for ServiceTitan — top builder A I dot com.",
]

SIZZLE = [
    "This is Top Builder AI — six self-learning agents that outclass ServiceTitan's own.",
    "Your phones never sleep, so that's two thousand, eight hundred, ninety-five dollars recovered after hours.",
    "Your trucks drive smarter, saving sixty minutes every single day.",
    "Your paperwork files itself, right to the correct customer and folder.",
    "Your techs quote on the spot, built right there on the phone.",
    "And every week, the agents learn your shop and get sharper, yet nothing happens without your approval.",
    "Six agents, one command center, getting smarter every month — top builder A I dot com.",
]

# Auto-mode explainer — the autonomous arc (mirrors HowItWorksAuto.tsx A1..A9).
AUTO = [
    "It's two fourteen in the morning, nobody's awake, but your agents are.",
    "Set an agent to Auto, and it runs all on its own.",
    "It reeds ServiceTitan and decides exactly what needs to happen.",
    "All of the numbers come from tested code, and the model only writes the words.",
    "Then it acts, with no waiting and no approval, it just books the job itself.",
    "Every action is signed, logged, and reversible, so you can undo any of it, anytime.",
    "It fails closed and only acts inside the limits you set, so anything bigger still asks you first.",
    "All six agents, running on their own around the clock, and learning your shop, getting sharper every week.",
    "Top Builder AI, the operating layer for ServiceTitan — top builder A I dot com.",
]

if __name__ == "__main__":
    print("\n[1/4] narration clips")
    ex_paths, ex_durs = ensure_clips("explainer", EXPLAINER)
    sz_paths, sz_durs = ensure_clips("sizzle", SIZZLE)
    au_paths, au_durs = ensure_clips("auto", AUTO)

    print("\n[2/4] voice-driven scene timing")
    timings = {
        "HowItWorks": scene_frames(ex_durs),
        "Demo": scene_frames(sz_durs),
        "Auto": scene_frames(au_durs),
    }
    write_timing(timings)

    print("\n[3/4] render (video follows voice)")
    render("render")             # Demo -> out/top-builder-ai-demo.mp4
    render("render:howitworks")  # HowItWorks -> out/top-builder-ai-how-it-works.mp4
    render("render:auto")        # HowItWorksAuto -> out/top-builder-ai-auto-mode.mp4

    print("\n[4/4] mux + encode")
    print("=== explainer ===")
    mux(OUT / "top-builder-ai-how-it-works.mp4", ex_paths, ex_durs, timings["HowItWorks"],
        DOWNLOADS / "Top-Builder-AI-how-it-works.mp4")
    print("=== sizzle ===")
    mux(OUT / "top-builder-ai-demo.mp4", sz_paths, sz_durs, timings["Demo"],
        DOWNLOADS / "Top-Builder-AI-demo.mp4")
    print("=== auto ===")
    mux(OUT / "top-builder-ai-auto-mode.mp4", au_paths, au_durs, timings["Auto"],
        DOWNLOADS / "Top-Builder-AI-auto-mode.mp4")

    print("\n[gate] UTMOS naturalness check")
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import score_mos  # noqa: PLC0415
        clips = sorted(VO.glob(f"*_{CLIP_VER}_*.mp3"))
        scores = [score_mos.score(c) for c in clips]
        if scores:
            mn = sum(scores) / len(scores)
            verdict = "PASS (human-grade)" if mn >= 4.0 else "below 4.0 gate"
            print(f"  batch mean UTMOS = {mn:.3f} over {len(scores)} clips  ->  {verdict}")
    except Exception as e:  # noqa: BLE001
        print(f"  (UTMOS gate skipped: {type(e).__name__}: {str(e)[:80]})")
    print("\nDONE — eleven_v3 voice (UTMOS-picked takes), picture locked to the narration.")
