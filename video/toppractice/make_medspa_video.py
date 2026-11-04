"""Assemble the final med spa cornerstone video: HeyGen INTRO (build/intro_medspa.mp4) + image-driven
BODY (vid_medspa_cornerstone) + reused generic OUTRO (build/outro.mp4). Then the INTEGRITY GATE:
ffmpeg decode-clean + duration >= 7 min. Writes build/medspaguide_final.mp4, copies to medspa-cornerstone.mp4."""
import importlib.util, pathlib, shutil, subprocess, sys
HERE = pathlib.Path(__file__).parent
def load(name):
    spec = importlib.util.spec_from_file_location(name, str(HERE / f"{name}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
ae = load("anim_engine"); vid = load("vid_medspa_cornerstone")

BUILD = HERE / "build"
body = BUILD / "medspaguide_body.mp4"
intro = BUILD / "intro_medspa.mp4"
outro = BUILD / "outro.mp4"
final = BUILD / "medspaguide_final.mp4"

if not (body.exists() and body.stat().st_size > 100000):
    secs = ae.render_body(vid.B, str(body), BUILD / "medspaguide", voice="blend")
    print(f"BODY {secs:.1f}s ({secs/60:.1f} min)")
else:
    print("body exists:", ae.ffprobe_dur(body), "s")

intro_p = str(intro) if intro.exists() else None
outro_p = str(outro) if outro.exists() else None
if not intro_p: print("WARN: no intro_medspa.mp4 - assembling without it")
if not outro_p: print("WARN: no outro.mp4 - assembling without it")
ae.assemble_final(intro_p, str(body), outro_p, str(final))

dur = ae.ffprobe_dur(final)
dec = subprocess.run(["ffmpeg", "-v", "error", "-i", str(final), "-f", "null", "-"],
                     capture_output=True, text=True)
clean = (dec.returncode == 0 and not dec.stderr.strip())
print("\n=== INTEGRITY GATE ===")
print(f"duration: {dur:.1f}s ({dur/60:.2f} min)  | need >= 420s")
print(f"decode-clean: {clean}  (ffmpeg -v error stderr: {dec.stderr.strip()[:200] or 'EMPTY'})")
ok = clean and dur >= 420
if ok:
    dest = HERE / "medspa-cornerstone.mp4"
    shutil.copy(final, dest)
    thumb = BUILD / "medspaguide_thumb.jpg"
    if thumb.exists():
        shutil.copy(thumb, HERE / "medspa-cornerstone-thumb.jpg")
    print(f"PASS -> {dest} ({dur/60:.2f} min)")
else:
    print("FAIL integrity gate.")
    sys.exit(2)
