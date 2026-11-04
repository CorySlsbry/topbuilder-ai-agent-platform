"""Generate the photoreal Imagen stills for the pricebook video. Run with GCLOUD_TOKEN (neuron-learnai)."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from imagen_gen import gen

OUT = pathlib.Path(__file__).parent / "build/img/pricebook"
OUT.mkdir(parents=True, exist_ok=True)

# One cohesive shoot — same style suffix on every prompt (the cohesion lever).
S = (" — photorealistic cinematic editorial photograph, premium, shallow depth of field, 35mm, "
     "soft natural light with a subtle indigo and emerald accent, muted sophisticated palette, "
     "real residential HVAC / plumbing / electrical contractor world, high detail, candid, "
     "no text, no logos, no watermarks, no on-screen graphics")

SHOTS = {
  "hero":        "a confident home-services contractor business owner, mid 40s, standing in a tidy shop office reviewing pricing on a tablet, work trucks visible through a window behind him",
  "pricebook":   "an overwhelmed contractor owner at a desk late in the day staring at a laptop spreadsheet of prices, slightly frustrated, warm desk lamp light",
  "materials":   "close up of copper line sets, refrigerant cylinders and rolls of sheet metal on a wholesale supply counter, an HVAC technician's hand reaching for them",
  "vendor":      "a printed vendor price-increase letter and an invoice lying on a contractor's desk next to a calculator and a coffee mug, morning light",
  "tech_quote":  "a friendly HVAC technician sitting at a homeowner's kitchen table presenting an itemized quote on a tablet to a married couple, warm domestic light",
  "margin_leak": "a contractor owner reviewing month-end profit and loss reports at a desk, looking concerned at thinner-than-expected margins, soft window light",
  "agent_review":"a contractor owner calmly reviewing a clean list of proposed price updates on a tablet and tapping approve, organized modern back office",
  "before_stress":"a tired contractor owner late at night at a cluttered desk, stressed, holding his head, dim office",
  "after_calm":  "the same contractor owner relaxed and confident in a bright organized office in the morning, calm and in control, coffee in hand",
  "handshake":   "a contractor owner shaking hands with a happy homeowner on a front porch after closing a job, genuine smiles, golden hour",
  "tablet_plate":"a contractor's hand holding a tablet with a blank bright clean screen, lots of empty negative space on the screen, neutral desk background, even soft light",
}

if __name__ == "__main__":
    done = 0
    for name, prompt in SHOTS.items():
        out = OUT / f"{name}.jpg"
        if out.exists() and out.stat().st_size > 50000:
            print("skip", name); done += 1; continue
        try:
            gen(prompt + S, str(out), ar="16:9")
            done += 1
        except Exception as e:
            print("ERR", name, repr(e)[:160])
    print(f"DONE {done}/{len(SHOTS)} -> {OUT}")
