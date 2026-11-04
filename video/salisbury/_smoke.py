"""Stage A smoke test: render one branded TITLE card + one DATA (stat) card to PNG.
Proves the re-themed anim_engine imports + draws correctly before we build the full pipeline."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)

OUT = HERE / "build"; OUT.mkdir(parents=True, exist_ok=True)

# 1) title card (mid-beat: lt=1.2 of a 3s beat so all fades are fully in)
img = ae.BG.copy().convert("RGBA")
ae.SCENES["title"](img, 1.2, 3.0, 1.0, {
    "eyebrow": "Fractional CFO for construction",
    "title": "What does a fractional CFO cost?",
    "sub": "The honest numbers for a $1M to $25M contractor"})
img.convert("RGB").save(OUT / "_smoke_title.png")
print("WROTE", OUT / "_smoke_title.png")

# 2) data / stat card
img2 = ae.BG.copy().convert("RGBA")
ae.SCENES["stat"](img2, 1.2, 3.0, 1.0, {
    "value": "$170K-$360K",
    "label": "A full-time construction CFO, all-in, per year",
    "source": "CFMA 2025 compensation surveys"})
img2.convert("RGB").save(OUT / "_smoke_stat.png")
print("WROTE", OUT / "_smoke_stat.png")

# 3) bonus: a compare table (data structure) + bookend card, to exercise more scenes
img3 = ae.BG.copy().convert("RGBA")
ae.SCENES["compare"](img3, 1.2, 4.0, 1.0, {
    "title": "Which role does a contractor need?",
    "cols": ["Fractional CFO", "Controller", "Bookkeeper"],
    "rows": [("Forward-looking cash plan", [True, False, False]),
             ("Job costing + WIP", [True, True, False]),
             ("Records the transactions", [True, True, True]),
             ("Bank / surety strategy", [True, False, False])]})
img3.convert("RGB").save(OUT / "_smoke_compare.png")
print("WROTE", OUT / "_smoke_compare.png")

ae.bookend_card("Salisbury CFO", "What a fractional CFO really costs", "salisburybookkeeping.com", str(OUT / "_smoke_bookend.png"))
print("WROTE", OUT / "_smoke_bookend.png")
print("SMOKE OK")
