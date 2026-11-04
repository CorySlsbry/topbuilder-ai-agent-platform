"""Generate the photoreal construction stills for the fractional-CFO-cost video body.
EVERY still goes through image_qa.qa_or_regen (no garbled text/logos, pertains, quality).
Salisbury cohesion style suffix baked into imagen_gen.styled. Writes build/img/cfocost/<key>.jpg."""
import importlib.util, json, pathlib
HERE = pathlib.Path(__file__).parent
def load(name):
    spec = importlib.util.spec_from_file_location(name, str(HERE / f"{name}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
ig = load("imagen_gen"); qa = load("image_qa")

OUT = HERE / "build" / "img" / "cfocost"; OUT.mkdir(parents=True, exist_ok=True)

# key -> (imagen subject, QA subject). Avoid screens/UI/logos (handled in style); prefer paper/people.
SHOTS = {
 "owner_worry": ("a construction company owner at a desk late afternoon, looking worried at a stack of "
                 "printed invoices and a calculator, rolled blueprints nearby",
                 "a stressed construction business owner reviewing bills at a desk"),
 "jobsite_frame": ("a custom home under construction at the framing stage, framers working, lumber stacks, "
                   "clear blue sky, wide cinematic shot",
                   "an active residential construction job site at framing stage"),
 "money_vs_seat": ("an empty modern executive office chair behind a clean desk in a contractor's office, "
                   "morning light, a hard hat resting on the desk",
                   "an empty executive office in a construction company"),
 "blueprints_desk": ("close up of a contractor's hands spreading blueprints and a printed cost estimate "
                     "across a wooden desk, pencil and scale ruler, warm light",
                     "contractor hands reviewing blueprints and cost estimates"),
 "wip_paper": ("a contractor and a financial advisor reviewing a printed spreadsheet of job numbers "
               "together at a conference table, pointing at a row, focused",
               "two people reviewing printed construction job-cost numbers together"),
 "cash_forecast": ("a financial professional writing on a printed 13 week cash flow plan on paper at a "
                   "desk, coffee cup, organized, calm and deliberate",
                   "someone working through a printed cash flow forecast on paper"),
 "draw_truck": ("a contractor's pickup truck parked at a job site at golden hour, materials in the bed, "
                "a partially built home in the background",
                "a contractor pickup truck at a construction site"),
 "margin_squeeze": ("close up of construction materials, copper wire spools and steel rebar bundles in a "
                    "supply yard, price tags removed, industrial",
                    "construction materials copper wire and steel rebar in a supply yard"),
 "decision_table": ("a construction business owner and an advisor shaking hands across a desk in a back "
                    "office, blueprints and printed reports between them, partnership feeling",
                    "a contractor and an advisor agreeing across a desk"),
 "bank_meeting": ("a confident construction company owner in a clean office holding a printed financial "
                  "report, looking at the camera area, professional and assured",
                  "a confident contractor holding a printed financial report"),
 "three_roles": ("three professionals working at a long shared desk in a construction company office, "
                 "papers and a ledger, collaborative, candid",
                 "a small construction finance team working together at a desk"),
 "owner_calm_after": ("a relaxed construction company owner leaning back at a tidy desk, organized binders "
                      "and a clean printed report, satisfied, warm evening light",
                      "a calm contractor at an organized desk with clean reports"),
 "xray_review": ("a financial advisor handing a printed report across a desk to a construction company "
                 "owner, both engaged, a written document with handwritten notes visible",
                 "an advisor handing a written report to a contractor"),
 "before_stress": ("a construction owner overwhelmed by a chaotic pile of papers and receipts on a desk, "
                   "cluttered, dim light, head in hand",
                   "a contractor overwhelmed by a messy pile of paperwork"),
 "after_clean": ("the same construction owner at a clean organized desk with neat labeled binders and a "
                 "single printed report, bright confident light",
                 "a contractor at a clean organized desk with neat reports"),
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
(HERE / "build" / "cfocost_image_qa.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
passed = sum(1 for v in results.values() if v.get("ok"))
print(f"\nDONE: {passed}/{len(SHOTS)} passed QA")
for k, v in results.items():
    print(f"  {k:18s} ok={v.get('ok')} {('cached' if v.get('cached') else v.get('reason',''))[:54]}")
