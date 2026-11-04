"""Build the collections video INTRO bookend (topic-specific). Reuses the generic outro from heygen/tbai_outro_framed.mp4."""
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

INTRO_VO = ("If your ServiceTitan aging report has invoices older than 60 days, and your QuickBooks "
            "balance doesn't match what ServiceTitan says is open, those two signals mean you're "
            "working from bad data before you've even started chasing. Here's how to fix that with AI.")
INTRO_CARD = {"eyebrow": "TOP BUILDER AI · COLLECTIONS",
              "title": "Automate your A/R collections",
              "sub": "Reconcile, prioritize, and close the 60-plus bucket"}

def build(stem, vo, card):
    card_png = OUT / f"{stem}_card.png"
    ae.bookend_card(card["eyebrow"], card["title"], card["sub"], str(card_png))
    raw = HEY_OUT / f"{stem}_avatar.mp4"
    if not (raw.exists() and raw.stat().st_size > 100000):
        hb.render_bookend(vo, stem)
    framed = OUT / f"{stem}_framed.mp4"
    fb.frame(str(raw), str(card_png), str(framed))
    print("INTRO BOOKEND READY ->", framed)
    return framed

if __name__ == "__main__":
    build("tbai_collections_intro", INTRO_VO, INTRO_CARD)
