"""Render the ServiceTitan dispatch/routing-margin vertical reel (1080x1920, ~60s).

Motion-graphics only (no image API): brand typographic cards + Ken Burns drift,
Cory's cloned voice per beat (ElevenLabs), ffmpeg composite. Self-contained,
idempotent (skips TTS/clips already rendered), crash-safe.

Promotes: https://topbuilderai.com/blog/servicetitan-ai-dispatch-routing-margin.html
Brand: Top Builder AI (indigo/emerald on near-black).
HONEST-METHOD framing (2026-07-19 default): describes the gap + the done-for-you
method, no shipped-self-serve-agent claim, no "eight agents" reference.
"""
import os, sys, json, subprocess, pathlib, urllib.request

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = pathlib.Path(r"C:\Users\you\Downloads\ServiceTitan Agent platform\video\tbai")
WORK = ROOT / "build" / "dispatch_margin_reel"
WORK.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "dispatch_margin_reel.mp4"
W, H, FPS = 1080, 1920, 30

sys.path.insert(0, r"C:\Users\you\.neuron-vault")
from secrets_vault import get
XI_KEY = get("ELEVENLABS_API_KEY")
VOICE = "REDACTED_ID"  # Cory clone (same blend as Neuron/Salisbury)

# Top Builder AI brand
BG_DEEP = (5, 5, 8)
BG = (8, 8, 10)
INDIGO = (99, 102, 241)
INDIGO_L = (139, 147, 255)
EMERALD = (52, 211, 153)
CREAM = (245, 246, 250)
MUTED = (148, 152, 168)

# beat = (key, narration [spoken], headline [on-screen], kicker, accent)
BEATS = [
    ("hook",
     "Your dispatch board looked full and profitable all day. Then payroll came in with more overtime than anyone expected.",
     "A full board.\nA thin margin week.",
     "SAME DAY. TWO NUMBERS.", INDIGO_L),
    ("formula",
     "ServiceTitan's own Dispatch Pro documentation is public about what it optimizes. Predicted job value, minus drive cost, equals total revenue. That's a revenue formula. Not a margin one.",
     "Revenue minus drive cost.\nNot margin.",
     "SERVICETITAN'S OWN FORMULA", EMERALD),
    ("gap",
     "It doesn't know a technician is twenty minutes from overtime. It doesn't know sending them to this call bumps a higher margin install off tomorrow's board.",
     "Overtime. Tomorrow's job.\nNot in the formula.",
     "THE GAP, BY THEIR OWN DOCS", INDIGO_L),
    ("example",
     "In one afternoon example, the top ranked technician wins on revenue by sixty five dollars. Count the overtime premium and the bumped install, and the other technician is the better call.",
     "Revenue winner by $65.\nMargin loser by more.",
     "THE TRADEOFF, MADE VISIBLE", EMERALD),
    ("fix",
     "We read the same dispatch board your team already runs, and add the overtime and margin numbers the formula leaves out. The dispatcher still makes every call.",
     "Same board.\nOne more number.",
     "DISPATCHER STILL DECIDES", INDIGO_L),
    ("cta",
     "Full breakdown, math and all, is on the blog. Link below.",
     "Read the full\nbreakdown.",
     "TOPBUILDERAI.COM/BLOG", EMERALD),
]


def font(sz, kind="bold"):
    cands = {
        "bold": [r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf"],
        "serif": [r"C:\Windows\Fonts\georgiab.ttf", r"C:\Windows\Fonts\georgia.ttf"],
        "reg": [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"],
    }[kind]
    for p in cands:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                pass
    return ImageFont.load_default()


def tts(text, out):
    if out.exists() and out.stat().st_size > 4000:
        print("  skip tts", out.name)
        return
    def call(model, settings):
        body = json.dumps({"text": text, "model_id": model, "voice_settings": settings}).encode()
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}?output_format=mp3_44100_192",
            data=body, method="POST",
            headers={"xi-api-key": XI_KEY, "Content-Type": "application/json"})
        return urllib.request.urlopen(req, timeout=180).read()
    try:
        data = call("eleven_v3", {"stability": 0.5, "similarity_boost": 0.75})
    except Exception as e:
        print("  v3 failed (%s) -> multilingual_v2" % repr(e)[:80])
        data = call("eleven_multilingual_v2", {"stability": 0.5, "similarity_boost": 0.75, "style": 0.0})
    out.write_bytes(data)
    print("  TTS", out.name, out.stat().st_size)


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def card(headline, kicker, accent, idx, total, path):
    """Typographic brand card, rendered oversized so ffmpeg zoompan has headroom."""
    CW, CH = int(W * 1.25), int(H * 1.25)
    im = Image.new("RGB", (CW, CH), BG_DEEP)
    d = ImageDraw.Draw(im)

    # vertical gradient near-black -> slightly lifted
    for y in range(CH):
        t = y / CH
        d.line([(0, y), (CW, y)], fill=(
            int(BG_DEEP[0] + (BG[0] - BG_DEEP[0]) * t),
            int(BG_DEEP[1] + (BG[1] - BG_DEEP[1]) * t),
            int(BG_DEEP[2] + (BG[2] - BG_DEEP[2]) * t)))

    # soft accent glow
    glow = Image.new("RGB", (CW, CH), BG_DEEP)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([CW * 0.05, CH * 0.16, CW * 0.95, CH * 0.62], fill=tuple(min(255, c) for c in accent))
    glow = glow.filter(ImageFilter.GaussianBlur(220))
    im = Image.blend(im, glow, 0.14)
    d = ImageDraw.Draw(im)

    mx = int(CW * 0.11)

    # wordmark
    f_mark = font(34, "bold")
    d.text((mx, int(CH * 0.11)), "TOP BUILDER", font=f_mark, fill=CREAM)
    d.text((mx + d.textlength("TOP BUILDER ", font=f_mark), int(CH * 0.11)), "AI", font=f_mark, fill=EMERALD)
    d.text((mx + d.textlength("TOP BUILDER AI", font=f_mark) + 16, int(CH * 0.11)),
           "|  ServiceTitan back office", font=font(28, "reg"), fill=MUTED)

    # kicker
    f_k = font(32, "bold")
    d.text((mx, int(CH * 0.30)), kicker, font=f_k, fill=accent)

    # accent rule
    d.rounded_rectangle([mx, int(CH * 0.345), mx + 150, int(CH * 0.345) + 9], radius=5, fill=accent)

    # headline (serif, brand voice) - auto-fit inside the ZOOM-SAFE box.
    zoom_max = 1.12
    safe_right = CW / 2 + (CW / (2 * zoom_max))
    maxw = int(safe_right - mx - 24)
    lines = headline.split("\n")
    size = 108
    while size > 46:
        f_h = font(size, "serif")
        if max(d.textlength(l, font=f_h) for l in lines) <= maxw:
            break
        size -= 4
    f_h = font(size, "serif")
    y = int(CH * 0.40)
    for line in lines:
        d.text((mx, y), line, font=f_h, fill=CREAM)
        y += int(size * 1.18)

    # progress pips
    px, py = mx, int(CH * 0.86)
    for i in range(total):
        on = i <= idx
        d.rounded_rectangle([px, py, px + (74 if on else 44), py + 8], radius=4,
                            fill=accent if on else (48, 50, 62))
        px += (90 if on else 60)

    im.save(path)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("FFMPEG FAIL:", " ".join(str(c) for c in cmd)[:200])
        print(r.stderr[-1200:])
        sys.exit(1)


def main():
    clips, total_d = [], 0.0
    for i, (key, narr, head, kick, accent) in enumerate(BEATS):
        print(f"[{i+1}/{len(BEATS)}] {key}")
        mp3 = WORK / f"{key}.mp3"
        tts(narr, mp3)
        d_a = dur(mp3)
        d_clip = round(d_a + 0.45, 2)  # small tail so speech never clips
        total_d += d_clip

        png = WORK / f"{key}.png"
        if not png.exists():
            card(head, kick, accent, i, len(BEATS), png)

        clip = WORK / f"{key}.mp4"
        if not clip.exists():
            frames = max(2, int(d_clip * FPS))
            vf = (f"zoompan=z='min(zoom+0.00045,1.12)':d={frames}:x='iw/2-(iw/zoom/2)':"
                  f"y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
                  f"fade=t=in:st=0:d=0.32,fade=t=out:st={max(0,d_clip-0.32):.2f}:d=0.32,"
                  f"format=yuv420p")
            run(["ffmpeg", "-y", "-loop", "1", "-i", str(png), "-i", str(mp3),
                 "-filter_complex", f"[0:v]{vf}[v]",
                 "-map", "[v]", "-map", "1:a",
                 "-af", f"apad,atrim=0:{d_clip},afade=t=out:st={max(0,d_clip-0.30):.2f}:d=0.30",
                 "-t", str(d_clip), "-r", str(FPS),
                 "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                 "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                 "-shortest", str(clip)])
        clips.append(clip)

    lst = WORK / "concat.txt"
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
         "-movflags", "+faststart", str(OUT)])

    final = dur(OUT)
    print(f"\nRENDERED {OUT}  ({final:.2f}s, target <= 60s)")
    chk = subprocess.run(["ffmpeg", "-v", "error", "-i", str(OUT), "-f", "null", "-"],
                         capture_output=True, text=True)
    print("DECODE:", "CLEAN" if not chk.stderr.strip() else "ERRORS:\n" + chk.stderr[-800:])


if __name__ == "__main__":
    main()
