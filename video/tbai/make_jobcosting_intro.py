"""Build ONLY the job-costing video INTRO bookend (the generic outro is reused from
tbai_outro_framed.mp4). Renders the digital twin via HeyGen, frames it onto a TBA-branded card.
Run with network enabled. Mirrors make_zeroinstall_intro.py."""
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

INTRO_VO = ("If you run ServiceTitan and QuickBooks, your company books look fine, but ask which jobs "
            "actually made money and the answer is a guess. Here is why job costing breaks between the "
            "two systems, and how to fix it.")
INTRO_CARD = {"eyebrow": "TOP BUILDER AI · JOB COSTING",
              "title": "Connect ServiceTitan to QuickBooks",
              "sub": "Automated job costing that finally tells the truth"}

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
    build("tbai_jobcosting_intro", INTRO_VO, INTRO_CARD)
