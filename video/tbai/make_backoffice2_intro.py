"""Frame the already-rendered Post-2-v2 intro twin (rendered via heygen_bookend.py directly)."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
def _load(n, p):
    s = importlib.util.spec_from_file_location(n, str(p)); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
ae = _load("ae", HERE / "anim_engine.py"); fb = _load("fb", HERE / "frame_bookend.py")
HEY_OUT = pathlib.Path("C:/Users/you/Downloads/AI Trainer/video/heygen")
OUT = HERE / "heygen"; OUT.mkdir(parents=True, exist_ok=True)

CARD = {"eyebrow": "TOP BUILDER AI · THE DIRECT ANSWER",
        "title": "What's the Best AI Back Office for ServiceTitan Shops?",
        "sub": "Invoicing, dispatch, and collections, without babysitting"}

if __name__ == "__main__":
    stem = "tbai_backoffice2_intro"
    card_png = OUT / f"{stem}_card.png"
    ae.bookend_card(CARD["eyebrow"], CARD["title"], CARD["sub"], str(card_png))
    raw = HEY_OUT / f"{stem}_avatar.mp4"
    if not (raw.exists() and raw.stat().st_size > 100000):
        raise SystemExit(f"raw avatar not found: {raw}")
    framed = OUT / f"{stem}_framed.mp4"
    fb.frame(str(raw), str(card_png), str(framed))
    print("INTRO READY ->", framed)
