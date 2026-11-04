"""Images for the 'AI back office for ServiceTitan' video. 5 new + reuse 6 from the pricebook set."""
import pathlib, shutil, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from imagen_gen import gen

OUT = pathlib.Path(__file__).parent / "build/img/backoffice"; OUT.mkdir(parents=True, exist_ok=True)
PB = pathlib.Path(__file__).parent / "build/img/pricebook"

S = (" — photorealistic cinematic editorial photograph, premium, shallow depth of field, 35mm, "
     "soft natural light with a subtle indigo and emerald accent, muted sophisticated palette, "
     "real residential HVAC / plumbing / electrical contractor world, high detail, candid, "
     "no text, no logos, no watermarks, no on-screen graphics")

NEW = {
  "frontoffice":   "a busy call-center service coordinator wearing a headset at a tidy dispatch desk taking customer calls, dispatch board on a monitor behind her, modern contractor office",
  "backoffice_pile":"a contractor business owner late at night at a desk buried under stacks of paper invoices, bills and spreadsheets, overwhelmed by back-office paperwork, dim warm lamp",
  "command_center":"a clean modern operations dashboard on a large monitor in a calm contractor back office, an owner standing confidently reviewing it, organized and in control",
  "bolton_mess":   "a frustrated contractor owner at a desk surrounded by many disconnected laptops, phones and sticky notes, juggling too many separate software tools, cluttered",
  "team":          "a small calm professional contractor back-office team working together at desks in a bright organized office, collaborative and unhurried",
}
REUSE = ["hero","margin_leak","agent_review","before_stress","after_calm","handshake"]

if __name__ == "__main__":
    for name in REUSE:
        s, d = PB/f"{name}.jpg", OUT/f"{name}.jpg"
        if s.exists() and not d.exists(): shutil.copy(s, d); print("reuse", name)
    done = 0
    for name, prompt in NEW.items():
        out = OUT/f"{name}.jpg"
        if out.exists() and out.stat().st_size > 50000: print("skip", name); done += 1; continue
        try: gen(prompt + S, str(out), ar="16:9"); done += 1
        except Exception as e: print("ERR", name, repr(e)[:150])
    print(f"DONE {done}/{len(NEW)} new + {len(REUSE)} reused -> {OUT}")
