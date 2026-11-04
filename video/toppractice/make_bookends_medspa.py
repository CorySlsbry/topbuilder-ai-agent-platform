"""Render the med spa cornerstone HeyGen avatar INTRO (topic-specific), frame it onto a brand card.
REUSES the generic Top Practice CFO outro (build/outro.mp4) from the vet run, so only the intro renders.
Cory's twin (look 67e134...), blend voice. Intro ~40 words. Writes framed build/intro_medspa.mp4."""
import importlib.util, pathlib, sys
HERE = pathlib.Path(__file__).parent
def load(name):
    spec = importlib.util.spec_from_file_location(name, str(HERE / f"{name}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
hb = load("heygen_bookend"); fb = load("frame_bookend"); ae = load("anim_engine")

BUILD = HERE / "build"; BUILD.mkdir(parents=True, exist_ok=True)

INTRO_LINE = ("What does a fractional CFO actually do for a med spa, and is it worth it? "
              "Let me give you the honest numbers, what the role covers, and how to tell when it is "
              "time to hire one for a practice your size. No fluff.")

intro_bg = BUILD / "intro_card_medspa.png"
ae.bookend_card("Fractional CFO for med spas",
                "What a fractional CFO really does",
                "What it covers, what it costs, when to hire", str(intro_bg))

intro_av = hb.render_bookend(INTRO_LINE, "medspaguide_intro")
fb.frame(str(intro_av), str(intro_bg), str(BUILD / "intro_medspa.mp4"))

if not (BUILD / "outro.mp4").exists():
    print("WARN: build/outro.mp4 (generic Top Practice CFO outro) missing - run make_bookends_vet first", file=sys.stderr)
print("MEDSPA INTRO DONE -> build/intro_medspa.mp4 (reusing build/outro.mp4)")
