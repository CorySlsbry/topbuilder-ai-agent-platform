"""Render a HeyGen digital-twin bookend (intro or outro) lip-synced to a cloned-voice mp3.
Reusable for any brand: pass the line, the avatar look id, and the output stem. Renders mp4 16:9
(NOT webm — the look isn't matting-trained), then you frame it with frame_bookend.py onto a brand card.

Usage:
  python heygen_bookend.py "<spoken line>" <out_stem> [avatar_id]
  -> writes heygen/<out_stem>_avatar.mp4 (raw twin) ; frame it next with frame_bookend.py

Keys read at runtime (never hardcode): HEYGEN_API_KEY in Content Engine/.env.
Voice: uses the cory-voice blend (Gemini Charon -> ElevenLabs STS -> clone). Swap the voice target in
voice_synth.py for a different owner. Keep intro lines ~40 words (~15s); outro ~27 words (~12s).
"""
from __future__ import annotations
import importlib.util, json, pathlib, sys, time, urllib.request, urllib.error, uuid

ROOT = pathlib.Path("C:/Users/you/Downloads/AI Trainer")        # <- per-project
OUT = ROOT / "video" / "heygen"; OUT.mkdir(parents=True, exist_ok=True)
DEFAULT_AVATAR = "REDACTED_ID"               # Cory's digital twin
ENV = "C:/Users/you/Downloads/Content Engine/.env"
VS_PATH = "C:/Users/you/.claude/skills/cory-voice/references/voice_synth.py"

def env_val(path, key):
    for line in pathlib.Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if s.startswith(key + "="):
            return s.split("=", 1)[1].strip().strip('"').strip("'")
    raise KeyError(key)

def api(url, hey, data=None, headers=None, method=None, timeout=180):
    h = {"X-Api-Key": hey}; h.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"), headers=h)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8','ignore')[:600]}"); raise

def render_bookend(line, stem, avatar_id=DEFAULT_AVATAR):
    hey = env_val(ENV, "HEYGEN_API_KEY")
    # 1) blend VO in the owner's cloned voice
    vo = OUT / f"{stem}_vo.mp3"
    if not (vo.exists() and vo.stat().st_size > 1000):
        spec = importlib.util.spec_from_file_location("vs", VS_PATH)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        print(f"synth VO ({len(line.split())} words)..."); m.blend(line, vo)
    # 2) upload audio asset (v3 multipart)
    b = uuid.uuid4().hex
    body = (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{stem}.mp3"\r\n'
            f"Content-Type: audio/mpeg\r\n\r\n").encode() + vo.read_bytes() + f"\r\n--{b}--\r\n".encode()
    ar = api("https://api.heygen.com/v3/assets", hey, data=body,
             headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    d = ar.get("data") or ar; asset_id = d.get("asset_id") or d.get("id")
    if not asset_id: print("NO ASSET:", json.dumps(ar)[:400]); sys.exit(1)
    # 3) render avatar_iv, 16:9, audio-driven (mutually exclusive with script+voice_id)
    r = api("https://api.heygen.com/v3/videos", hey, data=json.dumps({
        "type": "avatar", "avatar_id": avatar_id, "audio_asset_id": asset_id,
        "engine": {"type": "avatar_iv"}, "aspect_ratio": "16:9", "resolution": "1080p",
        "title": f"neuron-{stem}"}).encode(), headers={"Content-Type": "application/json"})
    rd = r.get("data") or r; vid = rd.get("video_id") or rd.get("id")
    if not vid: print("NO VIDEO ID:", json.dumps(r)[:400]); sys.exit(1)
    # 4) poll  (MOVIO_PAYMENT_INSUFFICIENT_CREDIT on failure = top up at app.heygen.com)
    url = None
    for i in range(150):
        time.sleep(8)
        st = api(f"https://api.heygen.com/v1/video_status.get?video_id={vid}", hey).get("data", {})
        print(f"[{i}] {st.get('status')}")
        if st.get("status") in ("completed", "success"): url = st.get("video_url") or st.get("url"); break
        if st.get("status") in ("failed", "error"): print("FAILED:", json.dumps(st)[:600]); sys.exit(1)
    if not url: print("timeout"); sys.exit(1)
    out = OUT / f"{stem}_avatar.mp4"; urllib.request.urlretrieve(url, out)
    print("WROTE", out, out.stat().st_size, "bytes"); return out

if __name__ == "__main__":
    line = sys.argv[1]; stem = sys.argv[2]
    avatar = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_AVATAR
    render_bookend(line, stem, avatar)
