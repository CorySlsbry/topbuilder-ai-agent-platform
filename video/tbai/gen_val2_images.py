"""Images for the 'True Job Margin' (value round 2) video. 7 new photoreal stills -> build/img/val2/.
Brand style: dark, indigo accent, real contractor world, no text in images."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from imagen_gen import gen

OUT = pathlib.Path(__file__).parent / "build/img/val2"; OUT.mkdir(parents=True, exist_ok=True)

S = (" — photorealistic cinematic editorial photograph, premium, shallow depth of field, 35mm, "
     "moody low-key lighting with a subtle indigo accent, muted sophisticated dark palette, "
     "real residential HVAC / plumbing / electrical contractor world, high detail, candid, "
     "no text, no logos, no watermarks")

NEW = {
  "pl_night":       "a contractor business owner alone at an office desk late at night studying printed financial statements with a calculator, brow furrowed, warm desk lamp against cool blue-indigo shadows" + S + ", no on-screen graphics",
  "jobsite_crew":   "two HVAC technicians installing a condenser unit beside a residential home, gauges and tools laid out, early evening golden light fading to dusk" + S + ", no on-screen graphics",
  "callback_van":   "a service van parked outside a suburban house at dusk, a technician walking up the driveway carrying a tool bag for a return visit, porch light on" + S + ", no on-screen graphics",
  "worked_job":     "a plumbing technician mid-job replacing a water heater in a tidy garage mechanical room, copper fittings and work light, focused" + S + ", no on-screen graphics",
  "office_manager": "a focused office manager at a clean contractor office desk on a quiet morning reviewing paperwork beside a large monitor, coffee mug, organized and calm" + S + ", no readable screen text",
  "dashboard_margin":"over-the-shoulder view of a modern dark analytics dashboard with abstract bar charts glowing on a desktop monitor in a contractor back office at night, indigo screen glow on the desk" + S.replace(", no text, no logos, no watermarks", ", abstract unreadable charts only, no readable text, no logos, no watermarks"),
  "analyzer_mockup":"a laptop on a contractor office desk displaying a sleek dark web calculator tool with glowing indigo accent panels and soft abstract charts, workshop softly blurred behind" + S.replace(", no text, no logos, no watermarks", ", abstract unreadable interface only, no readable text, no logos, no watermarks"),
}

if __name__ == "__main__":
    done = 0
    for name, prompt in NEW.items():
        out = OUT / f"{name}.jpg"
        if out.exists() and out.stat().st_size > 50000:
            print("skip", name); done += 1; continue
        try:
            gen(prompt, str(out), ar="16:9"); done += 1
        except Exception as e:
            print("ERR", name, repr(e)[:150])
    print(f"DONE {done}/{len(NEW)} -> {OUT}")
