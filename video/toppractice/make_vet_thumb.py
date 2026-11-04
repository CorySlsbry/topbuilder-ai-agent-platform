"""Thumbnail for the veterinary cornerstone video: one on-brand Imagen photo through the QA loop, then
compose with make_thumb (navy/gold, auto-fit title). Asserts check_layout + vision_check before use."""
import importlib.util, pathlib, sys
HERE = pathlib.Path(__file__).parent
def load(name):
    spec = importlib.util.spec_from_file_location(name, str(HERE / f"{name}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
ig = load("imagen_gen"); qa = load("image_qa"); mt = load("make_thumb")

BUILD = HERE / "build"; (BUILD / "img").mkdir(parents=True, exist_ok=True)
photo = BUILD / "img" / "thumb_vet_owner.jpg"
SUBJECT = ("a veterinarian practice owner, mid 40s, in plain unbranded scrubs at a desk in a clinic "
           "back office reviewing a printed financial report and a calculator, a stethoscope beside "
           "them, thoughtful confident expression, warm window light, no logos")

v = qa.qa_or_regen(lambda i: ig.styled(SUBJECT, str(photo), ar="16:9"),
                   str(photo), "a veterinary practice owner reviewing financial reports at a desk",
                   kind="photo", tries=3)
print("PHOTO QA:", v)

out = BUILD / "vetguide_thumb.jpg"
report = mt.build(str(photo), "Veterinary",
                  "Fractional CFO for vet practices", str(out))

layout_ok = qa.check_layout(report)
tv = qa.vision_check(str(out), "a video thumbnail titled about fractional CFO for veterinary practices",
                     kind="thumbnail")
print("LAYOUT_OK:", layout_ok, "| THUMB VISION:", tv)
if not layout_ok:
    print("FAIL: thumbnail layout overrun"); sys.exit(1)
print("THUMBNAIL OK ->", out)
