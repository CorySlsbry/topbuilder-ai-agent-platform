"""QA all collections images and regenerate any that fail vision check."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from image_qa import qa_or_regen
from imagen_gen import gen as _gen

IMG = pathlib.Path(__file__).parent / "build/img/collections"
S = (" -- photorealistic cinematic editorial photograph, premium, shallow depth of field, 35mm, "
     "soft natural light with a subtle indigo and emerald accent, muted sophisticated palette, "
     "real HVAC / plumbing / electrical contractor back-office world, high detail, candid, "
     "no text, no logos, no watermarks, no on-screen graphics")

SHOTS = {
  "hero":         "a professional HVAC contractor business owner sitting at a neat desk reviewing a printed aging report, looking serious but composed, morning office light, laptop open showing spreadsheet",
  "aging_pile":   "a contractor office desk with a neat stack of paper invoices and a laptop showing an accounts receivable aging spreadsheet, overhead warm light, organized but busy",
  "cash_worry":   "a trades contractor looking concerned at a mobile banking app showing a lower-than-expected balance, sitting at a back-office desk, afternoon light",
  "qbo_screen":   "a close-up of a laptop screen showing a clean QuickBooks Online accounts receivable dashboard with invoice rows, soft desk reflection, professional office setting",
  "st_invoice":   "a ServiceTitan technician in the field using a tablet to email an invoice to a homeowner after completing an HVAC installation job, outdoor natural light",
  "mismatch":     "two side-by-side laptop screens on a desk showing different financial figures for the same customer, an office manager looking puzzled, soft office lighting",
  "call_prompt":  "a friendly office receptionist in a trades company office on the phone using a call script on a tablet, professional, relaxed, daytime window light",
  "text_payment": "a hand holding a smartphone with a clean professional text message payment reminder and a payment link, light background, minimal",
  "ranked_queue": "a contractor business owner reviewing a prioritized task list on a tablet in a clean back office, approving action items one by one, confident expression",
  "escalation":   "an office manager at a desk flagging a paper invoice with a sticky note, discussing with a business owner nearby, organized professional environment",
  "before_stress":"a tired contractor owner late in the day at a cluttered desk, stressed expression, surrounded by unpaid invoice papers, dim warm office light",
  "after_clear":  "the same contractor owner relaxed and confident the next morning at an organized clean desk, cash flow chart visible on screen behind them, bright morning light",
  "handshake":    "a contractor and a commercial property manager shaking hands warmly in a bright modern office lobby, genuine business relationship, professional attire",
}

fails = []
for name, prompt in SHOTS.items():
    out = str(IMG / f"{name}.jpg")
    full_prompt = prompt + S
    def gen_fn(attempt, _p=full_prompt, _o=out):
        _gen(_p, _o, ar="16:9")
    result = qa_or_regen(gen_fn, out, name + " HVAC contractor context", kind="photo", tries=2)
    if not result.get("ok"):
        fails.append((name, result.get("reason", "?")))

print(f"QA DONE. Fails: {len(fails)}")
for n, r in fails:
    print(f"  FAIL {n}: {r}")
if not fails:
    print("ALL IMAGES PASS QA")
