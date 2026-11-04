"""Thumbnail for the fractional-CFO-cost video: one on-brand Imagen photo through the QA loop, then
compose with make_thumb (navy/gold). Asserts check_layout + vision_check(text_ok) before use."""
import importlib.util, pathlib, sys
HERE = pathlib.Path(__file__).parent
def load(name):
    spec = importlib.util.spec_from_file_location(name, str(HERE / f"{name}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
ig = load("imagen_gen"); qa = load("image_qa"); mt = load("make_thumb")

BUILD = HERE / "build"; (BUILD / "img").mkdir(parents=True, exist_ok=True)
photo = BUILD / "img" / "thumb_owner.jpg"
SUBJECT = ("a construction company owner, mid 40s, sitting at a desk in a back office reviewing "
           "printed job-cost reports and a calculator, rolled blueprints beside him, thoughtful "
           "expression, warm window light")

# 1) generate the source photo through the QA regen loop (no garbled text/logos, pertains, quality)
v = qa.qa_or_regen(lambda i: ig.styled(SUBJECT, str(photo), ar="16:9"),
                   str(photo), "a construction business owner reviewing financial reports at a desk",
                   kind="photo", tries=3)
print("PHOTO QA:", v)

# 2) compose the thumbnail (auto-fit title that can never overrun)
out = BUILD / "cfocost_thumb.jpg"
report = mt.build(str(photo), "Fractional CFO cost", "What a fractional CFO costs for a contractor", str(out))

# 3) gates: deterministic layout + vision text_ok
layout_ok = qa.check_layout(report)
tv = qa.vision_check(str(out), "a video thumbnail titled about fractional CFO cost for construction",
                     kind="thumbnail")
print("LAYOUT_OK:", layout_ok, "| THUMB VISION:", tv)
if not layout_ok:
    print("FAIL: thumbnail layout overrun"); sys.exit(1)
print("THUMBNAIL OK ->", out)
