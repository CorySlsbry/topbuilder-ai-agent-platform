"""CTA — single-beat outro clip for the ServiceTitan-alternative-small-trades long-form.
The ONE call to action, after the value has been delivered.
Usage: python vid_st_alt_small_trades_outro.py
"""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)

CACHE = HERE / "build/val3_stalt_outro"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = pathlib.Path("C:/Users/you/Downloads/ServiceTitan Agent platform/assets/video/longform/st-alt-small-trades/outro.mp4")

B = [
    {"vo": "If you run a one-to-ten person trades shop and you still can't answer what a job actually made, that's exactly what Top Builder OS was built to fix — scheduling, estimating, invoicing, and real job costing with CPA-ready books, in one system, on two flat monthly tiers with no per-seat charge and no implementation fee. Link's in the description — book a thirty-minute fit call.",
     "scene": "cta", "c": {"eyebrow": "Top Builder OS", "title": "Know What Every Job Made", "sub": "Two flat tiers · no implementation fee · live day-one", "url": "book.topbuilderai.com"}},
]

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    secs = ae.render_body(B, OUT, CACHE)
    print(f"OUTRO {secs:.1f}s -> {OUT}")
