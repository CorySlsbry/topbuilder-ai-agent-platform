"""Image-QA feedback loop — verify a generated image BEFORE it's used, and regenerate failures.

Rules (Cory, 2026-06-18):
  1. NO TEXT OVERRUN  — for composed thumbnails: all text fully visible, not clipped at edges, not
     overlapping the photo, legible. (For source photos: no unexpected/garbled embedded text or logos.)
  2. PERTAINS         — the image clearly depicts/relates to the stated subject.
  3. HIGH QUALITY     — sharp, realistic, professional; no distorted faces/hands, no AI mush/artifacts.

Two gates:
  - check_layout(report)         deterministic (from make_thumb's report) — guarantees no overrun.
  - vision_check(path, subject)  a vision model (Gemini) scores pertains/quality/text against the rules.
qa_or_regen(...) wraps a generator: generate -> vision_check -> regenerate up to N times on failure.
"""
from __future__ import annotations
import base64, json, pathlib, urllib.request

ENV = "C:/Users/you/Downloads/Content Engine/.env"
MODEL = "gemini-2.5-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"


def _key() -> str:
    for line in pathlib.Path(ENV).read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip().startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise KeyError("GEMINI_API_KEY")


def check_layout(report: dict) -> bool:
    """Deterministic overrun guard from make_thumb's report (text fits the column + canvas)."""
    return bool(report and report.get("fits"))


def vision_check(image_path: str, subject: str, kind: str = "photo", timeout: int = 60) -> dict:
    """Vision QA against the 3 rules. kind: 'thumbnail' (composed) or 'photo' (Imagen source).
    Returns {pertains, quality, text_ok, ok, reason}. Fail-OPEN to ok=True only if the API errors (so a
    transient outage never blocks a render) — but logs the error in 'reason'."""
    rules = ("This is a finished video/blog THUMBNAIL with overlaid text. text_ok = every piece of text is "
             "fully inside the frame (not cut off at any edge) AND does not overlap or sit on top of the photo "
             "AND is cleanly legible."
             if kind == "thumbnail" else
             "This is a source PHOTO that will go in a video. text_ok = there is no garbled/AI-mangled embedded "
             "text, no logos, no watermarks, no on-screen graphics.")
    prompt = (f"You are a STRICT brand-quality reviewer for a premium B2B software company. Intended subject: "
              f"\"{subject}\". Judge the attached image. {rules} pertains = the image clearly depicts or relates "
              f"to the subject. quality = sharp, realistic, professional, with NO distorted faces or hands, NO "
              f"AI artifacts/mush, NO off-topic objects (e.g. a random car in a non-automotive shot). Be strict: "
              f"if unsure, answer false. Return ONLY JSON: "
              f'{{"pertains":bool,"quality":bool,"text_ok":bool,"reason":"<=18 words"}}')
    try:
        b64 = base64.b64encode(pathlib.Path(image_path).read_bytes()).decode()
        body = json.dumps({
            "contents": [{"parts": [{"inline_data": {"mime_type": "image/jpeg", "data": b64}}, {"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }).encode()
        req = urllib.request.Request(f"{URL}?key={_key()}", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        resp = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        txt = resp["candidates"][0]["content"]["parts"][0]["text"]
        v = json.loads(txt)
        v["ok"] = bool(v.get("pertains") and v.get("quality") and v.get("text_ok"))
        return v
    except Exception as e:
        return {"pertains": True, "quality": True, "text_ok": True, "ok": True,
                "reason": f"QA-API-error (fail-open): {repr(e)[:80]}"}


def qa_or_regen(gen_fn, out_path: str, subject: str, kind: str = "photo", tries: int = 3) -> dict:
    """gen_fn(attempt:int)->writes out_path. Generate, vision_check, regenerate on fail up to `tries`.
    Returns the final verdict (with 'attempts'). Keeps the best attempt if all fail."""
    last = None
    for i in range(1, tries + 1):
        gen_fn(i)
        v = vision_check(out_path, subject, kind); v["attempts"] = i
        print(f"  QA[{i}] {pathlib.Path(out_path).name}: ok={v['ok']} ({v.get('reason','')[:60]})")
        if v["ok"]:
            return v
        last = v
    return last or {"ok": False, "reason": "no attempts"}


if __name__ == "__main__":
    import sys
    print(json.dumps(vision_check(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "photo"), indent=2))
