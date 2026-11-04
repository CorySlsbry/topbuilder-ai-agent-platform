"""Photoreal stills for the veterinary cornerstone video body. Every still goes through
image_qa.qa_or_regen (no garbled text/logos, pertains, quality). Writes build/img/vetguide/<key>.jpg."""
import importlib.util, json, pathlib
HERE = pathlib.Path(__file__).parent
def load(name):
    spec = importlib.util.spec_from_file_location(name, str(HERE / f"{name}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
ig = load("imagen_gen"); qa = load("image_qa")

OUT = HERE / "build" / "img" / "vetguide"; OUT.mkdir(parents=True, exist_ok=True)

# key -> (imagen subject, QA subject). Real veterinary settings + people; no screens/UI/text.
SHOTS = {
 "hero": ("a veterinary practice owner, a veterinarian in scrubs, standing in a clean modern animal "
          "hospital reception at morning light, calm and confident, looking toward the camera area",
          "a confident veterinarian practice owner in an animal hospital"),
 "owner_worry": ("a veterinarian practice owner at a back-office desk late afternoon, looking concerned "
                 "at a stack of printed financial statements and a calculator",
                 "a worried veterinary practice owner reviewing printed financials"),
 "exam_room": ("a veterinarian and a vet tech examining a calm dog on a stainless table in a bright "
               "veterinary exam room, candid and caring",
               "a veterinarian examining a dog in an exam room"),
 "surgery": ("a veterinary surgical suite with a veterinarian in surgical gown and cap focused during a "
             "procedure, sterile blue tones, professional",
             "a veterinarian in a surgical suite during a procedure"),
 "pharmacy": ("organized veterinary pharmacy shelves stocked with medication bottles and supplies in a "
              "clinic back room, neat and well lit",
              "organized veterinary pharmacy and supply shelves"),
 "service_lines": ("a veterinarian owner and a financial advisor reviewing a printed profit-by-service "
                   "report together at a table, pointing at a row, focused",
                   "two people reviewing a printed veterinary profit report"),
 "money_vs_seat": ("an empty executive office chair behind a clean desk in a veterinary clinic back "
                   "office, morning light, a stethoscope resting on the desk",
                   "an empty executive office chair in a veterinary clinic"),
 "dvm_comp": ("two veterinarians in scrubs talking with a practice manager in a clinic hallway, friendly "
              "and professional, clipboards in hand",
              "veterinarians and a practice manager talking in a clinic"),
 "cash_forecast": ("a financial professional writing on a printed thirteen week cash flow plan on paper "
                   "at a desk, coffee cup, organized and deliberate",
                   "someone working through a printed cash flow forecast on paper"),
 "exit_handshake": ("a veterinary practice owner and a buyer shaking hands across a desk in a clinic "
                    "office, printed reports between them, a partnership feeling",
                    "a veterinarian owner and a buyer shaking hands over reports"),
 "valuation_review": ("a confident veterinary practice owner holding a printed valuation report in a "
                      "clean clinic office, professional and assured, looking toward camera",
                      "a confident veterinarian holding a printed valuation report"),
 "three_roles": ("three professionals working together at a long shared desk in a veterinary clinic back "
                 "office, printed ledgers and reports, collaborative and candid",
                 "a small finance team working at a desk in a vet clinic"),
 "before_stress": ("a veterinarian practice owner overwhelmed by a chaotic pile of papers and invoices on "
                   "a cluttered desk, dim light, head in hand",
                   "a vet practice owner overwhelmed by messy paperwork"),
 "after_calm": ("the same veterinarian owner at a clean organized desk with neat labeled binders and a "
                "single printed report, bright confident evening light, relaxed",
                "a calm vet practice owner at an organized desk with clean reports"),
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
(HERE / "build" / "vetguide_image_qa.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
passed = sum(1 for v in results.values() if v.get("ok"))
print(f"\nDONE: {passed}/{len(SHOTS)} passed QA")
for k, v in results.items():
    print(f"  {k:18s} ok={v.get('ok')} {('cached' if v.get('cached') else v.get('reason',''))[:54]}")
