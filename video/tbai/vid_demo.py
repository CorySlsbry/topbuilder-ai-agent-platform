"""Top Builder AI PLATFORM DEMO walkthrough BODY — from landing/_content/demo-copy.md (the demo
video VO). Uses the REAL dashboard screenshots as scene photos (cc-*). Scenes restricted to confirmed
shapes in anim_engine.py. CTA is the final beat; do not append after it."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py")); ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)
IMG = str(HERE / "build/img/backoffice") + "/"
CAP = str((HERE / "../public/capture").resolve()).replace("\\", "/") + "/"
CACHE = HERE / "build/demo"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = HERE / "build/demo_body.mp4"
def P(n): return IMG + n + ".jpg"          # reusable photoreal back-office stills
def S(n): return CAP + n + ".png"          # real product screenshots

B = [
  # --- A. The gap ---
  {"vo": "Here is what Top Builder AI actually does. You already run ServiceTitan or Procore in the field, and QuickBooks for the books. The problem is the gap between them.",
   "scene": "split_photo", "c": {"photo": P("frontoffice"), "eyebrow": "The setup you already have", "title": "Field tools, plus QuickBooks", "sub": "ServiceTitan or Procore in the field. QuickBooks for the books."}},
  {"vo": "The job data is in one place, the financial truth is in another, and the back office spends its days reconciling the two by hand. Top Builder AI sits in that gap.",
   "scene": "split_photo", "c": {"photo": P("margin_leak"), "eyebrow": "Where the hours go", "title": "Two systems, reconciled by hand", "sub": "Job data here. Financial truth there. We sit in the middle."}},

  # --- B. What it reads, on real screens ---
  {"vo": "It reads the field data, it categorizes and costs every line, it reconciles it, and it pushes clean financial truth into QuickBooks.",
   "scene": "photo", "c": {"photo": S("cc-front-desk"), "eyebrow": "It reads what you already track", "title": "Jobs, time, invoices, materials", "sub": "Read, categorized, costed, reconciled"}},
  {"vo": "Eight agents handle the work no field software was built for. This is the Command Center, with every agent watching its own corner of the business.",
   "scene": "photo", "c": {"photo": S("cc-agent-controls"), "eyebrow": "Eight agents, one platform", "title": "The back office, run by agents", "sub": "Set each one Off, Approve-first, or Auto"}},

  # --- C. The agents, on their own screens ---
  {"vo": "Workforce watches your labor and your payroll, and surfaces the overtime nobody saw coming. Financial keeps the books to GAAP and projects your cash from real jobs.",
   "scene": "photo", "c": {"photo": S("cc-financial"), "eyebrow": "Money and people", "title": "Financial keeps the books honest", "sub": "Cash from real jobs. Labor and payroll watched."}},
  {"vo": "Inventory tracks materials so every ticket carries its true cost. Booking answers the phone around the clock, and Routing cuts the day's drive time.",
   "scene": "photo", "c": {"photo": S("cc-inventory"), "eyebrow": "Materials and dispatch", "title": "Inventory tracks the true cost", "sub": "Booking answers 24/7. Routing tightens the day."}},
  {"vo": "This is the Dispatch board, where Routing suggests the day's assignments and shows you the drive time it saved.",
   "scene": "photo", "c": {"photo": S("cc-dispatch"), "eyebrow": "Routing and Dispatch", "title": "A tighter day, suggested for you", "sub": "Assignments by drive time, with the time saved"}},
  {"vo": "Documents files the paperwork as it lands. Collections chases the aging worklist for you to approve. Pricebook holds your pricing honest as vendor costs move.",
   "scene": "photo", "c": {"photo": S("cc-booking"), "eyebrow": "Paperwork, A R, and pricing", "title": "The slow work, run continuously", "sub": "Documents file. Collections chase. Pricebook re-prices."}},

  # --- D. The firewall ---
  {"vo": "Every dollar and every hour you see is computed by tested code, then explained in plain language. The AI cannot change a number. It can only tell you what the number means.",
   "scene": "secure", "c": {"title": "The numbers are computed, not guessed", "items": [
     ("\U0001F512", "Tested code", "Every figure is computed by pure code"),
     ("\U0001F4AC", "AI explains only", "It narrates the number, never changes it"),
     ("↩", "Reversible", "Every action is logged and has an undo")]}},
  {"vo": "You decide how much it does on its own. Set each agent to Off, Approve-first, or Auto. Approve-first means nothing happens until you click yes, and every action is logged and reversible.",
   "scene": "photo", "c": {"photo": S("cc-agent-controls"), "eyebrow": "You stay in control", "title": "Off, Approve-first, or Auto", "sub": "Nothing happens until you click yes"}},

  # --- E. Leadership view ---
  {"vo": "Leadership sees the whole company at a glance. The Org view shows every person by department and which agents each one can use, and managers grant and revoke that access right there.",
   "scene": "photo", "c": {"photo": S("cc-org-2d"), "eyebrow": "The whole company, at a glance", "title": "Who can use which agent", "sub": "Granted by managers. Finance and HR walled off."}},
  {"vo": "Finance and HR stay walled off from the rest, and the view updates itself as people are hired and let go. The executive dashboard pulls it all together.",
   "scene": "photo", "c": {"photo": S("cc-executive"), "eyebrow": "Executive view", "title": "The business, end to end", "sub": "Updates itself as people are hired and let go"}},

  # --- F. Close ---
  {"vo": "We onboard a few shops at a time, hands-on, each quarter. If your back office is ready to run itself, claim a spot in the next quarterly cohort and watch it run against your own data.",
   "scene": "cta", "c": {"eyebrow": "Top Builder AI · for ServiceTitan contractors", "title": "See it run on your own data", "sub": "Claim a spot in the next quarterly cohort, board-ready-or-free", "url": "topbuilderai.com/demo.html"}},
]

if __name__ == "__main__":
    secs = ae.render_body(B, str(OUT), CACHE, voice="blend")
    print(f"BODY {secs:.1f}s ({secs/60:.1f} min), {len(B)} beats -> {OUT}")
