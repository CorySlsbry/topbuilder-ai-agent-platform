"""Assemble the final veterinary cornerstone long-form video:
  HeyGen avatar INTRO (build/intro.mp4) + image-driven BODY (vid_veterinary_cornerstone) + HeyGen avatar
  OUTRO (build/outro.mp4). Then the INTEGRITY GATE: ffmpeg decode-clean + duration >= 7 min.
Writes build/vetguide_final.mp4 and copies to veterinary-cornerstone.mp4 on pass."""
import importlib.util, pathlib, shutil, subprocess, sys
HERE = pathlib.Path(__file__).parent
def load(name):
    spec = importlib.util.spec_from_file_location(name, str(HERE / f"{name}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
ae = load("anim_engine"); vid = load("vid_veterinary_cornerstone")

BUILD = HERE / "build"
body = BUILD / "vetguide_body.mp4"
intro = BUILD / "intro.mp4"
outro = BUILD / "outro.mp4"
final = BUILD / "vetguide_final.mp4"

# 1) render the body if not already present
if not (body.exists() and body.stat().st_size > 100000):
    secs = ae.render_body(vid.B, str(body), BUILD / "vetguide", voice="blend")
    print(f"BODY {secs:.1f}s ({secs/60:.1f} min)")
else:
    print("body exists:", ae.ffprobe_dur(body), "s")

# 2) assemble intro + body + outro (skip a bookend gracefully if missing)
intro_p = str(intro) if intro.exists() else None
outro_p = str(outro) if outro.exists() else None
if not intro_p: print("WARN: no intro.mp4 (bookend missing) - assembling without it")
if not outro_p: print("WARN: no outro.mp4 (bookend missing) - assembling without it")
ae.assemble_final(intro_p, str(body), outro_p, str(final))

# 3) INTEGRITY GATE: decode-clean + duration >= 7 min
dur = ae.ffprobe_dur(final)
dec = subprocess.run(["ffmpeg", "-v", "error", "-i", str(final), "-f", "null", "-"],
                     capture_output=True, text=True)
clean = (dec.returncode == 0 and not dec.stderr.strip())
print("\n=== INTEGRITY GATE ===")
print(f"duration: {dur:.1f}s ({dur/60:.2f} min)  | need >= 420s")
print(f"decode-clean: {clean}  (ffmpeg -v error stderr: {dec.stderr.strip()[:200] or 'EMPTY'})")
ok = clean and dur >= 420
if ok:
    dest = HERE / "veterinary-cornerstone.mp4"
    shutil.copy(final, dest)
    thumb = BUILD / "vetguide_thumb.jpg"
    if thumb.exists():
        shutil.copy(thumb, HERE / "veterinary-cornerstone-thumb.jpg")
    print(f"PASS -> {dest} ({dur/60:.2f} min)")
else:
    print("FAIL integrity gate. Per the runbook: ship the POST without the video and log why.")
    sys.exit(2)
