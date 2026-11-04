"""Run after both body + intro renders complete. Assembles, integrity-checks, uploads, returns YouTube URL.
Usage: python finish_collections_video.py
Prints the YouTube URL on success. Exit code 0 = success, non-zero = failure."""
import importlib.util, pathlib, subprocess, sys, re
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

def size_ok(p):
    return p.exists() and p.stat().st_size > 100000

# Check body + outro
for p, name in [(BODY, "body"), (OUTRO, "outro")]:
    if not size_ok(p):
        print(f"ABORT: {name} not ready ({p})"); sys.exit(1)

intro = str(INTRO) if size_ok(INTRO) else None
print(f"Assembling: intro={'YES' if intro else 'SKIP (not ready, using body+outro)'}")

dur = ae.assemble_final(intro, str(BODY), str(OUTRO), str(FINAL))
print(f"Final: {dur:.1f}s ({dur/60:.1f} min) -> {FINAL}")

# INTEGRITY GATE
r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(FINAL), "-f", "null", "-"],
                   capture_output=True, text=True)
errors = (r.stderr or "").strip()
if errors:
    print(f"INTEGRITY FAIL (decode errors):\n{errors[:400]}"); sys.exit(2)
if dur < 420:
    print(f"INTEGRITY FAIL: {dur:.1f}s < 420s (7 min)"); sys.exit(3)
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
    capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print("UPLOAD ERROR:", result.stderr[:400]); sys.exit(4)

# Extract video ID
vid = None
for line in result.stdout.splitlines():
    m = re.search(r'youtu\.be/([A-Za-z0-9_-]{11})', line)
    if m: vid = m.group(1); break
    m = re.search(r'youtube\.com/watch\?v=([A-Za-z0-9_-]{11})', line)
    if m: vid = m.group(1); break

if vid:
    print(f"\nYOUTUBE_VIDEO_ID={vid}")
    print(f"URL: https://youtu.be/{vid}")
else:
    print("WARNING: could not extract video ID from upload output")
