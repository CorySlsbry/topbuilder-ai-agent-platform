"""Topic-specific HeyGen intro bookend for the Pricebook Pro vs. self-learning agent long-form.
Hook line via hooks.py + viral_score.py (see cycle log). Outro reuses the GENERIC tbai_outro_framed.mp4
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

# Ranked #1 hook (viral_score 92/100, via hooks.py+viral_score.py, real Gemini call) + the
# ladder's Q1 as the promise, inside the same <=15s intro (per the 2026-07-27 hook rule).
INTRO_VO = ("One vendor cost increase breaks fourteen flat-rate prices in ServiceTitan. So if you "
            "already pay for Pricebook Pro, here's the real question: does it actually catch that, "
            "or are you still exposed?")
INTRO_CARD = {"eyebrow": "TOP BUILDER AI · PRICEBOOK PRO",
              "title": "Pricebook Pro vs. a self-learning agent",
              "sub": "What each one actually updates"}

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
    build("tbai_pricebook_pro_intro", INTRO_VO, INTRO_CARD)
    print("INTRO DONE — reuse heygen/tbai_outro_framed.mp4 for the outro")
