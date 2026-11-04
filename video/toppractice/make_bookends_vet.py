"""Render the Top Practice CFO HeyGen avatar INTRO + OUTRO bookends for the veterinary cornerstone
video, then frame each onto a navy/gold brand title card. Cory's twin (look 67e134...), blend voice.
Intro ~40 words, outro ~30 words. Writes framed intro.mp4 + outro.mp4 in build/."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
def load(name):
    spec = importlib.util.spec_from_file_location(name, str(HERE / f"{name}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
hb = load("heygen_bookend"); fb = load("frame_bookend"); ae = load("anim_engine")

BUILD = HERE / "build"; BUILD.mkdir(parents=True, exist_ok=True)

INTRO_LINE = ("What does a fractional CFO actually do for a veterinary practice, and is it worth it? "
              "Let me give you the honest numbers, what the role covers, and how to tell when it is "
              "time to hire one for a practice your size. No fluff.")
OUTRO_LINE = ("If you want the honest picture for your practice, start with a fourteen day Financial "
              "X-ray. You get a written profit and cash read. Then you decide. Link is below.")

intro_bg = BUILD / "intro_card.png"
outro_bg = BUILD / "outro_card.png"
ae.bookend_card("Fractional CFO for veterinary practices",
                "What a fractional CFO really does",
                "What it covers, what it costs, when to hire", str(intro_bg))
ae.bookend_card("Top Practice CFO",
                "See your real numbers first",
                "toppracticecfo.com/how-we-work", str(outro_bg))

intro_av = hb.render_bookend(INTRO_LINE, "vetguide_intro")
outro_av = hb.render_bookend(OUTRO_LINE, "vetguide_outro")

fb.frame(str(intro_av), str(intro_bg), str(BUILD / "intro.mp4"))
fb.frame(str(outro_av), str(outro_bg), str(BUILD / "outro.mp4"))
print("BOOKENDS DONE -> build/intro.mp4 + build/outro.mp4")
