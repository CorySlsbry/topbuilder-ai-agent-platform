"""Build the Top Builder AI intro (topic-specific) + outro (generic, reusable) digital-twin bookends.
Renders the twin via HeyGen, frames each onto a TBA-branded card. Run with network enabled."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path)); m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m); return m
ae = _load("ae", HERE / "anim_engine.py")
hb = _load("hb", HERE / "heygen_bookend.py")
fb = _load("fb", HERE / "frame_bookend.py")

HEY_OUT = pathlib.Path("C:/Users/you/Downloads/AI Trainer/video/heygen")  # raw twins land here (hb.ROOT)
OUT = HERE / "heygen"; OUT.mkdir(parents=True, exist_ok=True)

# Topic-specific INTRO (~40 words, ~15s) — the hook for the pricebook video.
INTRO_VO = ("Your ServiceTitan pricebook decides every quote and every dollar of margin. "
            "But vendor costs creep up all year and the book never keeps up, so you're quietly "
            "quoting last spring's prices. Here's how to fix that, safely, with AI.")
INTRO_CARD = {"eyebrow": "TOP BUILDER AI · PRICEBOOK",
              "title": "Automate your ServiceTitan pricebook",
              "sub": "Keep material costs current when vendors raise prices"}

# Generic OUTRO (~28 words) — reuse across every Top Builder AI video.
OUTRO_VO = ("That's the idea: the back office ServiceTitan never automated, run by AI that learns your "
            "shop, and you approve every move. Read the guide, then book a call.")
OUTRO_CARD = {"eyebrow": "TOP BUILDER AI · FOR SERVICETITAN",
              "title": "Your back office, handled",
              "sub": "Book a 30-minute fit call — topbuilderai.com"}

def build(stem, vo, card, reuse_outro_twin=False):
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
    build("tbai_pricebook_intro", INTRO_VO, INTRO_CARD)
    build("tbai_outro", OUTRO_VO, OUTRO_CARD)   # generic — reused for future videos
    print("ALL BOOKENDS DONE")
