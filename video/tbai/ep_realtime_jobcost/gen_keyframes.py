import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\you\.claude\skills\geo-flywheel\references\engine")
import asset_gen  # noqa: E402

BRAND = "top-builder-ai"
CLUSTER = "realtime-job-cost-tracking"
OUT = Path(__file__).parent

BEATS = [
    ("kf_00_hook.png",
     "The bearded OWNER slumps at his blueprint-covered desk in the evening, staring at a tablet "
     "showing a big red downward arrow and the words CLOSED: LOST MONEY, his work truck visible "
     "through the window behind him, defeated exhausted expression, warm desk lamp light."),
    ("kf_01_arrive.png",
     "The hard-hat BOT strides into the office holding up a glowing handheld dashboard tablet with "
     "a live ticking cost readout, the OWNER looks up from his desk with surprised hopeful "
     "expression, morning light through the window."),
    ("kf_02_track.png",
     "The OWNER and the hard-hat BOT stand side by side looking at a large glowing wall dashboard "
     "showing two live bar meters labeled COMMITTED and ACTUAL cost ticking upward together, "
     "blueprints pinned on the wall around the screen, focused expressions."),
    ("kf_03_flag.png",
     "The hard-hat BOT points at the wall dashboard where one bar meter has just crossed a glowing "
     "red BUDGET LIMIT line, the OWNER leans in with a concerned but attentive expression, "
     "reaching to tap the screen to approve an action."),
    ("kf_04_cta.png",
     "The OWNER and the hard-hat BOT both give a thumbs up in front of the wall dashboard now "
     "showing a green PROFITABLE checkmark, tidy desk, bright sunny office, triumphant cinematic "
     "hero framing."),
]

for name, prompt in BEATS:
    out = OUT / name
    path = asset_gen.gen(prompt, out, ar="9:16", brand=BRAND, cluster=CLUSTER,
                         style=True, reuse=False)
    print(name, "->", path)
