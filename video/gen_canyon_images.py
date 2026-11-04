"""Photoreal 'day in the life of a Canyon Ridge Mechanical employee' stills via Vertex Imagen 4
(builder-ai-497610). Cohesive style suffix so the set feels like one shoot. Idempotent (skips existing).
Run:  GCLOUD_TOKEN=$(gcloud auth print-access-token --project builder-ai-497610) python video/gen_canyon_images.py
"""
import pathlib
import sys

sys.path.insert(0, "C:/Users/you/.claude/skills/video-generation/references")
import imagen_gen as ig  # noqa: E402

ig.PROJECT = "builder-ai-497610"
ig.URL = (
    "https://us-central1-aiplatform.googleapis.com/v1/projects/builder-ai-497610"
    "/locations/us-central1/publishers/google/models/imagen-4.0-generate-001:predict"
)

OUT = pathlib.Path("C:/Users/you/Downloads/ServiceTitan Agent platform/video/public/people")
OUT.mkdir(parents=True, exist_ok=True)
STYLE = (
    " — photorealistic cinematic editorial photograph, premium, shallow depth of field, 35mm, "
    "soft natural light with a subtle cool violet and cyan accent, muted sophisticated palette, "
    "high detail, candid, no text, no logos, no watermarks, no on-screen graphics"
)

SHOTS = {
    "dispatcher_morning": "a focused woman dispatcher in her thirties at a tidy desk in a mechanical contractor's office, early morning, looking at a computer screen, a coffee mug beside her",
    "phone_missed": "a close-up of a desk phone in a dim, empty early-morning contractor office, a notepad and pen beside it, quiet and still, nobody around",
    "tech_van": "a male HVAC service technician in a clean work uniform stepping out of a white service van in a suburban driveway, carrying a tool bag, soft morning light",
    "owner_desk": "a calm middle-aged male contractor business owner sitting at his office desk with a coffee, reviewing a laptop, early morning light through the blinds",
    "owner_home": "a relaxed middle-aged male contractor business owner walking out of his shop toward his pickup truck at golden hour, jacket over his shoulder, relieved and content",
}

for name, prompt in SHOTS.items():
    out = OUT / f"{name}.jpg"
    if out.exists() and out.stat().st_size > 50000:
        print("skip", name)
        continue
    ig.gen(prompt + STYLE, str(out), ar="16:9")
print("DONE images")
