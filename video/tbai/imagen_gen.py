"""Generate premium photoreal images via Vertex AI Imagen 4 (same model the Neuron app uses).
Auth via gcloud access token (project neuron-learnai). Output PNG/JPG. Cloud gen, no local strain.
Usage:
  python imagen_gen.py            # 1 test image -> build/img/_test.jpg
  from imagen_gen import gen; gen("a prompt", "out.jpg", ar="16:9")
"""
import base64, json, pathlib, subprocess, urllib.request, urllib.error

PROJECT = "neuron-learnai"
MODEL = "imagen-4.0-generate-001"
MODEL_ULTRA = "imagen-4.0-ultra-generate-001"  # HERO shots only (hook still / thumbnail source / chapter opens)
def _url(model):
    return (f"https://us-central1-aiplatform.googleapis.com/v1/projects/{PROJECT}"
            f"/locations/us-central1/publishers/google/models/{model}:predict")
URL = (f"https://us-central1-aiplatform.googleapis.com/v1/projects/{PROJECT}"
       f"/locations/us-central1/publishers/google/models/{MODEL}:predict")

import os
def _token():
    # allow a pre-fetched token via env (avoids gcloud-on-PATH issues from python subprocess)
    if os.environ.get("GCLOUD_TOKEN"):
        return os.environ["GCLOUD_TOKEN"].strip()
    r = subprocess.run("gcloud auth print-access-token --project " + PROJECT,
                       shell=True, capture_output=True, text=True)
    t = r.stdout.strip()
    if not t:
        raise RuntimeError("no gcloud token: " + (r.stderr or "")[:300])
    return t

def gen(prompt, out, ar="16:9", n=1, retry=2, model=None):
    """Generate one image to `out`. ar in 1:1|9:16|16:9|3:4|4:3.
    model: None=standard, "ultra"/MODEL_ULTRA for hero shots (2x cost, use sparingly)."""
    m = MODEL_ULTRA if model in ("ultra", MODEL_ULTRA) else (model or MODEL)
    out = pathlib.Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({
        "instances": [{"prompt": prompt[:1500]}],
        "parameters": {"sampleCount": n, "aspectRatio": ar, "safetySetting": "block_only_high",
                       "personGeneration": "allow_adult"},
    }).encode()
    last = None
    for attempt in range(retry + 1):
        try:
            req = urllib.request.Request(_url(m), data=body, method="POST",
                headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"})
            resp = json.loads(urllib.request.urlopen(req, timeout=180).read())
            preds = resp.get("predictions") or []
            if not preds or not preds[0].get("bytesBase64Encoded"):
                raise RuntimeError("no image in response: " + json.dumps(resp)[:300])
            out.write_bytes(base64.b64decode(preds[0]["bytesBase64Encoded"]))
            print("IMG", out.name, out.stat().st_size, "bytes")
            return str(out)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode('utf-8','ignore')[:400]}"
            print("  retry", attempt, last)
        except Exception as e:
            last = repr(e); print("  retry", attempt, last)
    raise RuntimeError("gen failed: " + str(last))

if __name__ == "__main__":
    gen("Photorealistic, cinematic: a stressed small-business owner in a busy dental front office at dusk, "
        "phone ringing unanswered on the desk, warm interior light, shallow depth of field, premium editorial photography, "
        "muted palette with subtle violet accent lighting, 35mm, high detail",
        "build/img/_test.jpg", ar="16:9")
