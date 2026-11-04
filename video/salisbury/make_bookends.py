"""Render the Salisbury CFO HeyGen avatar INTRO + OUTRO bookends for the fractional-CFO-cost video,
then frame each onto a navy/gold brand title card. Cory's twin (look 67e134...), blend voice.
Intro ~40 words, outro ~27 words. Writes framed intro.mp4 + outro.mp4 in build/."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
def load(name):
    spec = importlib.util.spec_from_file_location(name, str(HERE / f"{name}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
hb = load("heygen_bookend"); fb = load("frame_bookend"); ae = load("anim_engine")

BUILD = HERE / "build"; BUILD.mkdir(parents=True, exist_ok=True)

INTRO_LINE = ("What does a fractional CFO actually cost for a construction company? "
              "Let me give you the honest number, where it comes from, and how to tell if it is "
              "worth it for a contractor your size. No fluff.")
OUTRO_LINE = ("If you want the real number for your company, start with a fourteen day Financial X-Ray. "
              "You get a written leak list. Then you decide. Link is below.")

# Brand title cards (text left, avatar composited right)
intro_bg = BUILD / "intro_card.png"
outro_bg = BUILD / "outro_card.png"
ae.bookend_card("Fractional CFO for construction",
                "What a fractional CFO really costs",
                "The honest 2026 number, by engagement type", str(intro_bg))
ae.bookend_card("Salisbury CFO",
                "See your real number first",
                "salisburybookkeeping.com/contact", str(outro_bg))

intro_av = hb.render_bookend(INTRO_LINE, "cfocost_intro")
outro_av = hb.render_bookend(OUTRO_LINE, "cfocost_outro")

fb.frame(str(intro_av), str(intro_bg), str(BUILD / "intro.mp4"))
fb.frame(str(outro_av), str(outro_bg), str(BUILD / "outro.mp4"))
print("BOOKENDS DONE -> build/intro.mp4 + build/outro.mp4")
