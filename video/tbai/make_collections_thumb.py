"""Generate + QA the collections thumbnail."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from make_thumb import build as thumb_build
from image_qa import check_layout, vision_check

IMG = pathlib.Path(__file__).parent / "build/img/collections"
OUT_DIR = pathlib.Path("C:/Users/you/Downloads/ServiceTitan Agent platform/landing/blog")
THUMB_OUT = str(OUT_DIR / "_thumb_collections.jpg")

# Use hero (confirmed QA-pass) as the source photo
PHOTO = str(IMG / "hero.jpg")

if __name__ == "__main__":
    report = thumb_build(
        PHOTO,
        "TOP BUILDER AI",
        "Automate A/R Collections: The ServiceTitan Invoice Aging Playbook",
        THUMB_OUT
    )
    print("Thumb report:", report)
    layout_ok = check_layout(report)
    print("Layout OK:", layout_ok)
    if layout_ok:
        v = vision_check(THUMB_OUT, "ServiceTitan HVAC contractor A/R collections thumbnail", kind="thumbnail")
        print("Vision QA:", v)
        if v.get("ok"):
            print("THUMBNAIL PASS ->", THUMB_OUT)
        else:
            print("THUMBNAIL vision FAIL (keeping anyway):", v.get("reason"))
    else:
        print("THUMBNAIL layout FAIL (text overrun detected)")
