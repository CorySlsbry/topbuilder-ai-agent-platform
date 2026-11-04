#!/usr/bin/env python3
"""Build the 3 Top Builder OS shorts as REAL Pixar animation (Veo), not Ken Burns stills.
HARD RULE (Cory 2026-07-29): every reel/short beat is a genuine generated motion clip.

Fires all beats' Veo requests in parallel, polls, then runs short_engine per short
(short_engine now plays a `video` beat full-bleed; the still is only a fallback).
No price anywhere in the copy (Cory 2026-07-29).
"""
import base64, json, os, subprocess, sys, time, urllib.request
from pathlib import Path

ENG = Path.home() / ".claude/skills/geo-flywheel/references/engine"
RUN = Path(r"C:/Users/you/Downloads/ServiceTitan Agent platform/video/tbai/build/tbos-alt-run")
PROJECT = "builder-ai-497610"
MODEL = "veo-3.0-fast-generate-001"
BASE = (f"https://us-central1-aiplatform.googleapis.com/v1/projects/{PROJECT}"
        f"/locations/us-central1/publishers/google/models/{MODEL}")
STYLE = {"bg": [8, 8, 10], "accent": [99, 102, 241], "ink": [237, 241, 246],
         "wordmark": "TOP BUILDER OS", "cta_url": "topbuilderai.com", "cta_mode": "overlay"}
PIX = ("3D Pixar-style animated movie shot, vertical full-frame composition, cinematic warm "
       "lighting, shallow depth of field, expressive characters, real fluid motion. ")
TAIL = " No text, no on-screen graphics, no logos, no watermark, no phone or device frame."

# short -> list of beats (kind, vo text, on-screen caption, veo motion prompt, fallback still)
SHORTS = {
 "tbos_short1": [
  ("hook", "ServiceTitan is incredible software, built for a shop ten times your size.",
   "Built for a shop 10x your size",
   "a friendly small three-person home-services crew stands dwarfed beneath a towering oversized "
   "enterprise control-room wall of glowing dashboards; they crane their necks upward, a little "
   "overwhelmed but good-humored, slow camera tilt up", "s1a-enterprise-vast.png"),
  ("body", "For a small crew, it's built for scale and complexity you'll never grow into.",
   "Scale you'll never grow into",
   "a small-shop owner in his forties sits at a desk overwhelmed, comically scrolling an "
   "over-complicated software dashboard packed with hundreds of tiny buttons that keep multiplying, "
   "he rubs his forehead, subtle push-in", "s1b-pricetag.png"),
  ("body", "There's a system built for YOUR size instead, the jobs and the books in one place.",
   "One system, your size",
   "the same owner now calm and relieved holding a single clean tablet with one tidy simple screen, "
   "he smiles and nods, tools and a small work van softly behind him, gentle camera move",
   "s1c-relief.png"),
 ],
 "tbos_short2": [
  ("hook", "Jobber and Housecall Pro are great. But they hand your books to QuickBooks.",
   "They hand your books to QuickBooks",
   "a cheerful contractor hands a big overflowing box of receipts and paperwork across a counter to "
   "a stiff boxy robotic ledger machine, conveyor-belt handoff, papers fluttering, dynamic motion",
   "s2a-handoff.png"),
  ("body", "And QuickBooks has no real job costing. No cost codes, no committed costs.",
   "No real job costing",
   "a puzzled shop owner stares at a floating translucent spreadsheet with obvious missing "
   "puzzle-piece gaps and question marks drifting up around him, he scratches his head, slow push-in",
   "s2b-gaps.png"),
  ("body", "One system costs every job at true burden, automatically. So you finally know what it made.",
   "Every job, true cost",
   "the owner's face lights up with a big smile as a clean glowing per-job profit card assembles "
   "itself piece by piece in front of him and a green check mark pops in, satisfying motion, push-in",
   "s2c-clarity.png"),
 ],
 "tbos_short3": [
  ("hook", "It's 11pm, and you just closed the books in minutes, not hours.",
   "Books closed in minutes",
   "late evening warm desk-lamp glow, a tired but relieved small-business owner closes his laptop "
   "with a satisfied sigh and a small smile after finishing fast, cozy home office, gentle push-in",
   "s3a-night-relief.png"),
  ("body", "Your crew runs the whole job from their phones in the field.",
   "Run it from the field",
   "bright sunny job site, a cheerful field technician in a ball cap taps and swipes a work tablet "
   "logging a job with an easy grin, a work van behind him, lively motion", "s3b-field.png"),
  ("body", "Know what every job made, without a spreadsheet or a bookkeeper. All in one system.",
   "Know what every job made",
   "a contractor owner looks at a softly glowing floating summary of finished jobs each with a small "
   "green profit badge and nods with genuine satisfaction, smooth camera move", "s3c-know.png"),
 ],
}


def token():
    t = os.environ.get("GCLOUD_TOKEN")
    if t:
        return t.strip()
    return subprocess.run("gcloud auth print-access-token --project " + PROJECT, shell=True,
                          capture_output=True, text=True, timeout=30).stdout.strip()


def submit(tok, prompt):
    body = json.dumps({"instances": [{"prompt": (PIX + prompt + TAIL)[:1000]}],
                       "parameters": {"aspectRatio": "9:16", "durationSeconds": 8,
                                      "sampleCount": 1, "generateAudio": False}}).encode()
    hdr = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    req = urllib.request.Request(f"{BASE}:predictLongRunning", data=body, headers=hdr, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=60).read()).get("name")


def fetch(tok, op):
    hdr = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    r = urllib.request.Request(f"{BASE}:fetchPredictOperation", method="POST",
                               data=json.dumps({"operationName": op}).encode(), headers=hdr)
    return json.loads(urllib.request.urlopen(r, timeout=60).read())


def main():
    # ⛔ COST KILL-SWITCH — FAIL CLOSED (Cory 2026-08-11).
    # This script talks DIRECTLY to Vertex `veo-3.0-fast-generate-001` via :predictLongRunning and
    # had NO gate of any kind: main() submitted every beat unconditionally. At 9 clips x 8s x
    # ~$0.125/s that is ~$9 per run, and it survived the 2026-08-10 Veo->fal.ai migration untouched
    # because that migration only gated engine/veo_gen.py. The flywheel's own shorts-cycle.md even
    # named this file as the reference implementation, so an agent following the docs would spend
    # Veo money while believing the pipeline was on fal.ai.
    # fal.ai kling (~$0.029/s via engine/veo_gen.py) is the sanctioned backend. Vertex is opt-in ONLY.
    if (os.environ.get("VIDEO_BACKEND") or "falai").strip().lower() != "veo":
        sys.exit("Vertex Veo path is DISABLED (fal.ai is the default backend, ~4x cheaper).\n"
                 "Use: python engine/veo_gen.py --lane top-builder-ai --prompt <p> --out <clip> --seconds 8\n"
                 "To deliberately spend Veo money anyway, re-run with VIDEO_BACKEND=veo.")
    tok = token()
    assert tok, "no gcloud token"
    jobs = []  # (short, idx, clip_path, prompt, op|None)
    for short, beats in SHORTS.items():
        for i, (_k, _vo, _cap, prompt, _still) in enumerate(beats):
            jobs.append({"short": short, "idx": i, "clip": str(RUN / f"{short}_veo{i}.mp4"),
                         "prompt": prompt, "op": None, "done": False})
    print(f"submitting {len(jobs)} Veo clips...")
    for j in jobs:
        try:
            j["op"] = submit(tok, j["prompt"]); print(f"  {j['short']}#{j['idx']} op ok")
        except Exception as e:
            print(f"  {j['short']}#{j['idx']} SUBMIT FAIL {str(e)[:90]}")
        time.sleep(2)
    # poll up to ~18 min
    deadline = 108  # * 10s
    for loop in range(deadline):
        time.sleep(10)
        if loop % 6 == 0:
            tok = token()  # refresh hourly-ish
        pending = [j for j in jobs if not j["done"]]
        if not pending:
            break
        for j in pending:
            if not j["op"]:
                try:
                    j["op"] = submit(tok, j["prompt"])
                except Exception:
                    continue
            try:
                res = fetch(tok, j["op"])
            except Exception:
                continue
            if res.get("done"):
                vids = (res.get("response", {}).get("videos") or [])
                b64 = vids[0].get("bytesBase64Encoded") if vids else None
                if b64:
                    Path(j["clip"]).write_bytes(base64.b64decode(b64)); j["done"] = True
                    print(f"  DONE {j['short']}#{j['idx']} -> {os.path.getsize(j['clip'])//1024}KB")
                else:
                    j["done"] = True; j["clip"] = None
                    print(f"  EMPTY {j['short']}#{j['idx']}: {json.dumps(res)[:120]}")
        if loop % 3 == 0:
            print(f"  ...{sum(j['done'] for j in jobs)}/{len(jobs)} done (t+{(loop+1)*10}s)")
    # build specs + render
    ok = {(j["short"], j["idx"]): (j["clip"] if j["done"] and j["clip"] else None) for j in jobs}
    for short, beats in SHORTS.items():
        hook = None; body = []
        for i, (kind, vo, cap, _p, still) in enumerate(beats):
            seg = {"text": vo, "caption": cap}
            clip = ok.get((short, i))
            if clip and os.path.exists(clip):
                seg["video"] = clip
            sp = RUN / still
            if sp.exists():
                seg["image"] = str(sp)
            if kind == "hook":
                hook = seg
            else:
                body.append(seg)
        spec = {"lane": "top-builder-ai", "style": STYLE, "hook": hook, "body": body,
                "cta": {"text": "See it -> topbuilderai.com"}}
        spec_p = RUN / f"{short}_veo.json"
        spec_p.write_text(json.dumps(spec, indent=1), encoding="utf-8")
        out = RUN / f"{short}.mp4"
        print(f"\n=== render {short} (video beats: {sum(1 for i in range(len(beats)) if ok.get((short,i)))}/{len(beats)}) ===")
        r = subprocess.run([sys.executable, str(ENG / "short_engine.py"), "--spec", str(spec_p),
                            "--out", str(out)], capture_output=True, text=True)
        print((r.stdout or "")[-300:], (r.stderr or "")[-400:])
    print("\nALL DONE")


if __name__ == "__main__":
    main()
