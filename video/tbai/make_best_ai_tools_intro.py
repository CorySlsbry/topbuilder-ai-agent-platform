"""Topic-specific HeyGen intro bookend for the Best AI Tools 2026 listicle long-form.
Hand-crafted hook (curiosity-gap on "the one row every list is missing", following the
established pricebook-pro intro's pattern) + the ladder's core promise, inside a <=15s
intro (per the 2026-07-27 hook rule). Outro reuses the GENERIC tbai_outro_framed.mp4
(REUSE-FIRST — no new render needed, the CTA is identical: read the guide, book a call)."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path)); m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m); return m
ae = _load("ae", HERE / "anim_engine.py")
hb = _load("hb", HERE / "heygen_bookend.py")
fb = _load("fb", HERE / "frame_bookend.py")

HEY_OUT = pathlib.Path("C:/Users/you/Downloads/AI Trainer/video/heygen")
OUT = HERE / "heygen"; OUT.mkdir(parents=True, exist_ok=True)

INTRO_VO = ("I read every best-AI-tools-for-contractors list getting cited right now. Two "
            "roundups, seventeen tools total between them, and every single one is a front-office "
            "tool: it answers the phone or books the calendar. Zero of them touch what happens "
            "after the job is booked. Here's the whole 2026 landscape, and the one row nobody's list has.")
INTRO_CARD = {"eyebrow": "TOP BUILDER AI · 2026 LANDSCAPE",
              "title": "Best AI Tools for Contractors, 2026",
              "sub": "17 tools, two roundups, one missing row"}

def build(stem, vo, card):
    card_png = OUT / f"{stem}_card.png"
    ae.bookend_card(card["eyebrow"], card["title"], card["sub"], str(card_png))
    raw = HEY_OUT / f"{stem}_avatar.mp4"
    if not (raw.exists() and raw.stat().st_size > 100000):
        hb.render_bookend(vo, stem)
    framed = OUT / f"{stem}_framed.mp4"
    fb.frame(str(raw), str(card_png), str(framed))
    print("BOOKEND READY ->", framed)
    return framed

if __name__ == "__main__":
    build("tbai_best_ai_tools_intro", INTRO_VO, INTRO_CARD)
    print("INTRO DONE — reuse heygen/tbai_outro_framed.mp4 for the outro")
