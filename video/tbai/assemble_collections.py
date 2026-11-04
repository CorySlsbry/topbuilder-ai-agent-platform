"""Assemble + integrity-check + upload the collections video. Run after body + intro renders complete."""
import importlib.util, pathlib, subprocess, sys
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)

INTRO  = HERE / "heygen/tbai_collections_intro_framed.mp4"
BODY   = HERE / "build/collections_body.mp4"
OUTRO  = HERE / "heygen/tbai_outro_framed.mp4"
FINAL  = HERE / "build/collections_final.mp4"
DESC   = HERE / "build/collections_desc.txt"

TITLE  = "How to Automate Invoice Collections for Your ServiceTitan Shop: The A/R Aging Playbook (2026)"
TAGS   = ("ServiceTitan,HVAC business,accounts receivable,collections automation,contractor cash flow,"
          "QuickBooks ServiceTitan,AI contractors,field service management,invoice collections,"
          "HVAC invoicing,plumbing contractor,electrical contractor,ServiceTitan AI,back office automation,"
          "A/R aging,contractor finance,Top Builder AI")

def check_ready():
    missing = [p for p in [BODY, OUTRO] if not (p.exists() and p.stat().st_size > 100000)]
    if missing:
        print("NOT READY — missing:", [str(p) for p in missing]); return False
    if not (INTRO.exists() and INTRO.stat().st_size > 100000):
        print("WARNING: intro not ready — assembling without it (body+outro only)")
    return True

if __name__ == "__main__":
    if not check_ready(): sys.exit(1)

    intro = str(INTRO) if (INTRO.exists() and INTRO.stat().st_size > 100000) else None
    print(f"Assembling: intro={'YES' if intro else 'SKIP'}, body=YES, outro=YES")

    dur = ae.assemble_final(intro, str(BODY), str(OUTRO), str(FINAL))
    print(f"Final video: {dur:.1f}s ({dur/60:.1f} min)")

    # INTEGRITY GATE: decode-clean + ≥ 7 min
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(FINAL), "-f", "null", "-"],
                       capture_output=True, text=True)
    errors = (r.stderr or "").strip()
    if errors:
        print("INTEGRITY FAIL (ffmpeg decode errors):\n", errors[:500])
        sys.exit(2)
    if dur < 420:  # 7 min
        print(f"INTEGRITY FAIL: duration {dur:.1f}s < 420s (7 min) — not posting")
        sys.exit(3)
    print(f"INTEGRITY PASS: {dur:.1f}s, decode-clean")

    # UPLOAD
    result = subprocess.run(
        [sys.executable, str(HERE / "yt_upload.py"),
         "--channel", "salisbury",
         "--file", str(FINAL),
         "--title", TITLE,
         "--desc-file", str(DESC),
         "--tags", TAGS,
         "--privacy", "public"],
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print("UPLOAD ERROR:", result.stderr[:500])
        sys.exit(4)

    # Extract the youtu.be URL from stdout
    for line in result.stdout.splitlines():
        if "youtu.be" in line or "youtube.com" in line:
            print("VIDEO URL:", line.strip())
            break
