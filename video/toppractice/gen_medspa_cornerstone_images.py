"""Photoreal stills for the med spa cornerstone video body. Every still goes through
image_qa.qa_or_regen (no garbled text/logos, pertains, quality). Writes build/img/medspaguide/<key>.jpg."""
import importlib.util, json, pathlib
HERE = pathlib.Path(__file__).parent
def load(name):
    spec = importlib.util.spec_from_file_location(name, str(HERE / f"{name}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
ig = load("imagen_gen"); qa = load("image_qa")

OUT = HERE / "build" / "img" / "medspaguide"; OUT.mkdir(parents=True, exist_ok=True)

SHOTS = {
 "hero": ("a confident med spa owner, a female aesthetic nurse practitioner in a clean white clinical "
          "coat, standing in a bright modern med spa reception at morning light, looking toward camera",
          "a confident med spa owner in a modern med spa reception"),
 "owner_worry": ("a med spa owner at a back-office desk late afternoon, looking concerned at a stack of "
                 "printed financial statements and a calculator",
                 "a worried med spa owner reviewing printed financials"),
 "treatment_room": ("a calm bright med spa treatment room, an aesthetic provider in gloves attending to a "
                    "relaxed client reclining in a treatment chair, soft clinical light",
                    "a med spa treatment room with a provider and a relaxed client"),
 "injectables": ("close up of an aesthetic nurse's gloved hands preparing a small cosmetic injectable "
                 "syringe on a clean tray in a clinical aesthetics setting, sterile and precise",
                 "gloved hands preparing a cosmetic injectable on a clean tray"),
 "laser_device": ("a sleek modern aesthetic laser treatment machine in a clean med spa room, premium "
                  "equipment, soft light, no people",
                  "a modern aesthetic laser device in a med spa room"),
 "retail_shelf": ("organized premium skincare retail shelves in a med spa front lobby, neat product "
                  "rows, elegant and well lit",
                  "organized premium skincare retail shelves in a med spa"),
 "service_lines": ("a med spa owner and a financial advisor reviewing a printed profit-by-service report "
                   "together at a table, pointing at a row, focused",
                   "two people reviewing a printed med spa profit report"),
 "money_vs_seat": ("an empty executive office chair behind a clean desk in a med spa back office, "
                   "morning light, a folded white clinical coat resting on the desk",
                   "an empty executive office chair in a med spa office"),
 "provider_comp": ("a med spa owner talking with an aesthetic nurse injector in a clean clinic hallway, "
                   "friendly and professional, clipboards in hand",
                   "a med spa owner and an injector talking in a clinic hallway"),
 "cash_forecast": ("a financial professional writing on a printed thirteen week cash flow plan on paper "
                   "at a desk, coffee cup, organized and deliberate",
                   "someone working through a printed cash flow forecast on paper"),
 "valuation_review": ("a confident med spa owner holding a printed valuation report in a clean elegant "
                      "clinic office, professional and assured, looking toward camera",
                      "a confident med spa owner holding a printed valuation report"),
 "exit_handshake": ("a med spa owner and a buyer shaking hands across a desk in a clinic office, printed "
                    "reports between them, a partnership feeling",
                    "a med spa owner and a buyer shaking hands over reports"),
 "before_stress": ("a med spa owner overwhelmed by a chaotic pile of papers and invoices on a cluttered "
                   "desk, dim light, head in hand",
                   "a med spa owner overwhelmed by messy paperwork"),
 "after_calm": ("a relaxed med spa owner in plain unbranded professional clothing at a clean organized "
                "desk, neat labeled binders and a single printed financial report, warm confident "
                "evening light, no logos",
                "a calm med spa owner at an organized desk with clean reports"),
}

results = {}
for key, (subj, qsubj) in SHOTS.items():
    out = OUT / f"{key}.jpg"
    if out.exists() and out.stat().st_size > 50000:
        print("skip (exists):", key); results[key] = {"ok": True, "cached": True}; continue
    print("=== generating:", key)
    v = qa.qa_or_regen(lambda i, s=subj, o=out: ig.styled(s, str(o), ar="16:9"),
                       str(out), qsubj, kind="photo", tries=3)
    results[key] = v
(HERE / "build" / "medspaguide_image_qa.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
passed = sum(1 for v in results.values() if v.get("ok"))
print(f"\nDONE: {passed}/{len(SHOTS)} passed QA")
for k, v in results.items():
    print(f"  {k:18s} ok={v.get('ok')} {('cached' if v.get('cached') else v.get('reason',''))[:54]}")
