"""Render the Post-2 (AI back office) intro twin + frame it. Reuses the generic outro already rendered."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
def _load(n, p):
    s = importlib.util.spec_from_file_location(n, str(p)); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
ae = _load("ae", HERE / "anim_engine.py"); hb = _load("hb", HERE / "heygen_bookend.py"); fb = _load("fb", HERE / "frame_bookend.py")
HEY_OUT = pathlib.Path("C:/Users/you/Downloads/AI Trainer/video/heygen")
OUT = HERE / "heygen"; OUT.mkdir(parents=True, exist_ok=True)

INTRO_VO = ("ServiceTitan runs your front office: the calls, the schedule, the dispatch. But the back "
            "office, the money, materials, people and paperwork, still runs on you. Here are the eight "
            "AI agents that finally run it for you.")
CARD = {"eyebrow": "TOP BUILDER AI · THE BACK OFFICE",
        "title": "The AI back office for ServiceTitan",
        "sub": "The agents ServiceTitan has no answer for"}

if __name__ == "__main__":
    stem = "tbai_backoffice_intro"
    card_png = OUT / f"{stem}_card.png"
    ae.bookend_card(CARD["eyebrow"], CARD["title"], CARD["sub"], str(card_png))
    raw = HEY_OUT / f"{stem}_avatar.mp4"
    if not (raw.exists() and raw.stat().st_size > 100000):
        hb.render_bookend(INTRO_VO, stem)
    framed = OUT / f"{stem}_framed.mp4"
    fb.frame(str(raw), str(card_png), str(framed))
    print("INTRO READY ->", framed)
