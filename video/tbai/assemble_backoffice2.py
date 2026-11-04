"""Assemble + integrity-check the 'best AI back office for ServiceTitan shops' out-answer video.
Does NOT upload — audio_mix + thumbnail run first, then finish_backoffice2_upload.py uploads the mixed file."""
import importlib.util, pathlib, subprocess, sys
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)

INTRO = HERE / "heygen/tbai_backoffice2_intro_framed.mp4"
BODY  = HERE / "build/backoffice2_body.mp4"
OUTRO = HERE / "heygen/tbai_outro_framed.mp4"
FINAL = HERE / "build/backoffice2_final.mp4"

def size_ok(p):
    return p.exists() and p.stat().st_size > 100000

if __name__ == "__main__":
    missing = [p for p in [INTRO, BODY, OUTRO] if not size_ok(p)]
    if missing:
        print("NOT READY - missing:", [str(p) for p in missing]); sys.exit(1)

    dur = ae.assemble_final(str(INTRO), str(BODY), str(OUTRO), str(FINAL))
    print(f"Final video: {dur:.1f}s ({dur/60:.1f} min)")

    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(FINAL), "-f", "null", "-"],
                       capture_output=True, text=True)
    errors = (r.stderr or "").strip()
    if errors:
        print("INTEGRITY FAIL (ffmpeg decode errors):\n", errors[:800]); sys.exit(2)
    if dur < 420:
        print(f"INTEGRITY FAIL: duration {dur:.1f}s < 420s (7 min) - not posting"); sys.exit(3)
    print(f"INTEGRITY PASS: {dur:.1f}s, decode-clean")
