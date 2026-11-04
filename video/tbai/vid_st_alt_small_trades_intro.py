"""HOOK — single-beat intro clip for the ServiceTitan-alternative-small-trades long-form.
The hook's only job is to stop the scroll before the body teaches anything.
Usage: python vid_st_alt_small_trades_intro.py
"""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)

CACHE = HERE / "build/val3_stalt_intro"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = pathlib.Path("C:/Users/you/Downloads/ServiceTitan Agent platform/assets/video/longform/st-alt-small-trades/intro.mp4")

B = [
    {"vo": "A two-truck HVAC shop can face a major upfront implementation just to get on ServiceTitan, before the real work even starts. And the tool that's actually priced for them, Jobber or Housecall Pro, still can't tell them what a job made. I'm going to show you why that gap exists, and exactly what a one-to-ten person crew should run instead.",
     "scene": "hook", "c": {"icon": "\U0001F527", "title": "The Best ServiceTitan\nAlternative for Small Crews", "sub": "Why a two-truck shop shouldn't buy enterprise software", "pulse": True}},
]

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    secs = ae.render_body(B, OUT, CACHE)
    print(f"INTRO {secs:.1f}s -> {OUT}")
