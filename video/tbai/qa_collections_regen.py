"""Targeted regen for collections images that failed QA — screen-free prompts to avoid logo/text issues."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from image_qa import qa_or_regen, vision_check
from imagen_gen import gen as _gen

IMG = pathlib.Path(__file__).parent / "build/img/collections"

# Style suffix — explicitly bars any screen/monitor faces to prevent logo/garbled-text failures
S = (" — photorealistic cinematic editorial photograph, premium, shallow depth of field, 35mm, "
     "soft natural light with a subtle indigo and emerald accent, muted sophisticated palette, "
     "HVAC / plumbing contractor setting (back office, trucks, job site, ductwork, tools), "
     "high detail, candid, NO screens or monitors facing camera, no visible UI, "
     "no text anywhere in the image, no logos, no watermarks, no on-screen graphics")

# Revised prompts: avoid screens, make HVAC context unmistakable
SHOTS = {
  "hero":         "a confident middle-aged HVAC business owner standing in his shop office surrounded by HVAC equipment manuals, work-order folders, and field tools on shelves behind him, looking professional and thoughtful, warm workshop light",
  "aging_pile":   "a cluttered contractor back-office desk with a stack of paper invoices and work orders, an overflowing inbox tray, sticky notes, and a coffee mug, warm overhead light, HVAC service company context",
  "qbo_screen":   "a contractor accountant or bookkeeper at a clean desk writing in a ledger or looking at printed financial statements, professional business office, framed HVAC license on the wall, morning light",
  "st_invoice":   "an HVAC technician in a branded company uniform crouching next to an outdoor AC condenser unit at a residential home, writing notes on a work clipboard, afternoon light, suburban neighborhood",
  "mismatch":     "a contractor office manager at a desk holding two printed reports and comparing them side by side with a frustrated expression, two piles of paper representing different records, warm office light",
  "call_prompt":  "a professional office manager at a trades company, sitting at a desk, on the phone with a notepad open in front of them, warm natural window light, no visible screens, relaxed and focused",
  "text_payment": "a contractor's hand holding a mobile phone showing a notification screen with a received payment confirmation, phone tilted at angle, clean neutral background, soft light, no app logos visible",
  "ranked_queue": "a contractor business owner at a desk reviewing a printed priority checklist with checkboxes, pen in hand, organized back office, HVAC unit visible in background through glass partition",
  "escalation":   "a contractor owner sitting across from an office manager at a meeting table, reviewing a thick folder of invoices together with serious expressions, professional office environment, daytime",
  "before_stress":"a tired male contractor owner in his forties late at night at a desk covered with paper invoices and folders, looking exhausted and stressed, dim desk lamp, no phone or screen visible",
  "after_clear":  "the same contractor owner in his forties, next morning, relaxed and confident at an organized clean desk, cup of coffee, sunlight coming through window, calm expression, minimal paperwork",
}

fails = []
for name, prompt in SHOTS.items():
    out = str(IMG / f"{name}.jpg")
    full_prompt = prompt + S
    print(f"\nRegenerating: {name}")
    def gen_fn(attempt, _p=full_prompt, _o=out):
        _gen(_p, _o, ar="16:9")
    result = qa_or_regen(gen_fn, out, name + " HVAC contractor context", kind="photo", tries=3)
    if not result.get("ok"):
        fails.append((name, result.get("reason", "?")))

print(f"\nREGEN QA DONE. Remaining fails: {len(fails)}")
for n, r in fails:
    print(f"  FAIL {n}: {r}")
if not fails:
    print("ALL REGENERATED IMAGES PASS QA")
