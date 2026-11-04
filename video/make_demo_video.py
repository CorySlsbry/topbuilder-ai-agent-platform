"""Premium ~80s SALES DEMO video for Cory's call with Alex.

Shows Top Builder AI working on a REAL ServiceTitan contractor (the live seeded demo,
"Canyon Ridge Mechanical") — actual captured product screens with Ken Burns motion +
Cory's voice (the cory-voice BLEND: Gemini Charon flow -> ElevenLabs STS into his clone)
+ brand title/CTA cards. Money-forward for a CPA-channel partner.

Reuses the proven synth from scripts/add_voiceover.py. Idempotent: caches VO + per-seg
clips, so a re-run resumes. Run with the sandbox disabled (network for TTS/STS):
    python video/make_demo_video.py
Output: video/demo_alex/top-builder-ai-demo-alex.mp4  (+ copied to Downloads).
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

VIDEO = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(VIDEO / "scripts"))
import add_voiceover as av  # noqa: E402  — synth_scene (blend), ffprobe_dur, keys/voice already loaded

av.BLEND_TAKES = 1  # one take per line = faster for a same-day deliverable (still the blend)

IMG = VIDEO / "public"
WORK = VIDEO / "demo_alex"
WORK.mkdir(exist_ok=True)
DOWNLOADS = pathlib.Path("C:/Users/you/Downloads")
FONT_BOLD = VIDEO.parent / "marketing" / "flyers" / "fonts" / "InstrumentSans-Bold.ttf"
FONT_REG = VIDEO.parent / "marketing" / "flyers" / "fonts" / "InstrumentSans-Regular.ttf"
W, H, FPS = 1920, 1080, 30
LEAD, TAIL = 0.45, 0.85
INK = (10, 13, 26)
IND = (99, 102, 241)
EME = (52, 211, 153)

# ---- the storyboard: one real screen + one smooth narration line per beat (money-forward for Alex) ----
SEGMENTS = [
    {"k": "morning", "img": "people/dispatcher_morning.jpg",
     "vo": "It's just after six, and Maria, their dispatcher, is already behind — the overnight calls are stacked up, waiting for her."},
    {"k": "phone", "img": "people/phone_missed.jpg",
     "vo": "Four of them came into their ServiceTitan overnight, and like most shops, two had quietly slipped to voicemail."},
    {"k": "book", "img": "capture/cc-booking.png",
     "vo": "But Top Builder AI was already reading their ServiceTitan. It answered every call — and here's the booking, drafted, the customer matched, the margin already checked."},
    {"k": "approve", "img": "capture/cc-front-desk.png",
     "vo": "Maria reviews it from one screen, taps approve, and it writes straight back into ServiceTitan — signed, logged, and reversible. Three thousand, two hundred and sixty dollars recovered before breakfast."},
    {"k": "field", "img": "people/tech_van.jpg",
     "vo": "Out in the field, her techs are routed tighter — the dispatch agent shaved the drive time on its own, and nobody had to touch the board."},
    {"k": "owner", "img": "people/owner_desk.jpg",
     "vo": "And by the time the owner sits down with his coffee, the hard part is already done for him."},
    {"k": "fin", "img": "capture/cc-financial.png",
     "vo": "The financial agent has flagged a hundred and nineteen thousand dollars in margin leakage — project by project — before it ever reached a month-end close."},
    {"k": "exec", "img": "capture/cc-executive.png",
     "vo": "Across the whole shop, in a single pass, the agents surfaced a hundred and forty-three thousand dollars of value the back office never used to see."},
    {"k": "safe", "img": "capture/cc-agent-controls.png",
     "vo": "And nothing happens without a human — every number computed, never guessed, every action logged and reversible, getting a little sharper every week."},
    {"k": "after", "img": "people/owner_home.jpg",
     "vo": "So the back office runs itself, the team is less stressed, and the owner is actually home for dinner."},
]
INTRO_VO = "Alex — here's a normal morning at Canyon Ridge Mechanical, with Top Builder AI quietly running the back office on their ServiceTitan."
OUTRO_VO = "That's the back office ServiceTitan can't run. Let's put it on a real contractor's numbers. Top builder A I dot com."


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)


def vo_clip(key: str, text: str) -> tuple[pathlib.Path, float]:
    clip = WORK / f"vo_{key}.mp3"
    if not (clip.exists() and clip.stat().st_size > 2000):
        print(f"  voice [{key}]: {text[:64]}...")
        av.synth_scene(text, clip)
    return clip, av.ffprobe_dur(clip)


def make_card(out: pathlib.Path, eyebrow: str, title_lines: list[str], sub: str) -> None:
    from PIL import Image, ImageDraw, ImageFont
    # efficient vertical wash: 1px-wide gradient column resized to full frame
    grad = Image.new("RGB", (1, H), INK)
    gpx = grad.load()
    for y in range(H):
        t = y / H
        gpx[0, y] = (int(INK[0] + (26 - INK[0]) * t), int(INK[1] + (32 - INK[1]) * t), int(INK[2] + (66 - INK[2]) * t))
    img = grad.resize((W, H))
    # emerald->indigo accent bar down the left edge
    bar = Image.new("RGB", (1, H), IND)
    bpx = bar.load()
    for y in range(H):
        t = y / H
        bpx[0, y] = (int(IND[0] + (EME[0] - IND[0]) * t), int(IND[1] + (EME[1] - IND[1]) * t), int(IND[2] + (EME[2] - IND[2]) * t))
    img.paste(bar.resize((10, H)), (0, 0))
    d = ImageDraw.Draw(img)
    f_eye = ImageFont.truetype(str(FONT_BOLD), 30)
    f_title = ImageFont.truetype(str(FONT_BOLD), 92)
    f_sub = ImageFont.truetype(str(FONT_REG), 38)
    d.text((140, 300), eyebrow.upper(), font=f_eye, fill=EME)
    y = 350
    for ln in title_lines:
        d.text((140, y), ln, font=f_title, fill=(244, 244, 246))
        y += 108
    d.text((140, y + 30), sub, font=f_sub, fill=(154, 163, 196))
    # brand wordmark tile top-left
    d.rounded_rectangle([140, 150, 196, 206], radius=14, fill=IND)
    d.text((210, 158), "TOP BUILDER AI", font=ImageFont.truetype(str(FONT_BOLD), 30), fill=(244, 244, 246))
    img.save(out)


def card_clip(key: str, png: pathlib.Path, vo: pathlib.Path, dur: float) -> pathlib.Path:
    out = WORK / f"seg_{key}.mp4"
    run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(png), "-i", str(vo),
        "-filter_complex", f"[0:v]scale={W}:{H},format=yuv420p,fade=t=in:st=0:d=0.4,fade=t=out:st={dur-0.5:.2f}:d=0.5,setsar=1[v];[1:a]adelay=400|400,apad[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", "-r", str(FPS),
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", str(out),
    ])
    return out


def screen_clip(key: str, img: pathlib.Path, vo: pathlib.Path, dur: float) -> pathlib.Path:
    out = WORK / f"seg_{key}.mp4"
    frames = round(dur * FPS)
    vf = (
        f"[0:v]scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
        f"zoompan=z='min(zoom+0.00045,1.09)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
        f"format=yuv420p,fade=t=in:st=0:d=0.35,fade=t=out:st={dur-0.45:.2f}:d=0.45,setsar=1[v];"
        f"[1:a]adelay={int(LEAD*1000)}|{int(LEAD*1000)},apad[a]"
    )
    run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(img), "-i", str(vo),
        "-filter_complex", vf, "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", "-r", str(FPS),
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", str(out),
    ])
    return out


def main() -> None:
    print("[1/4] voice (cory blend) + cards")
    intro_vo, intro_d = vo_clip("intro", INTRO_VO)
    outro_vo, outro_d = vo_clip("outro", OUTRO_VO)
    title_png, cta_png = WORK / "title.png", WORK / "cta.png"
    make_card(title_png, "A morning at Canyon Ridge Mechanical",
              ["The back office,", "running itself."], "Top Builder AI  ·  on top of ServiceTitan")
    make_card(cta_png, "The back office ServiceTitan can't run",
              ["See it on your", "own numbers."], "topbuilderai.com")

    print("[2/4] render segments")
    clips: list[pathlib.Path] = []
    clips.append(card_clip("00intro", title_png, intro_vo, LEAD + intro_d + 0.7))
    for s in SEGMENTS:
        vo, d = vo_clip(s["k"], s["vo"])
        clips.append(screen_clip(s["k"], IMG / s["img"], vo, LEAD + d + TAIL))
    clips.append(card_clip("99cta", cta_png, outro_vo, LEAD + outro_d + 1.2))

    print("[3/4] concat")
    listf = WORK / "concat.txt"
    listf.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    final = WORK / "top-builder-ai-demo-alex.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listf),
         "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
         "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", str(final)])

    print("[4/4] verify + copy")
    run(["ffmpeg", "-v", "error", "-i", str(final), "-f", "null", "-"])  # decode-check (header probe isn't enough)
    dur = av.ffprobe_dur(final)
    dest = DOWNLOADS / "Top-Builder-AI-demo-for-Alex.mp4"
    import shutil
    shutil.copy(final, dest)
    print(f"DONE  {final}  ({dur:.1f}s)  ->  {dest}")


if __name__ == "__main__":
    main()
