"""CUT BACK-OFFICE HOURS WITH AI (no new hire) video BODY — from
landing/_content/blog-2-cut-back-office-hours-with-ai-without-hiring.md (its Companion video script).
Reuses the backoffice image set (no new image-gen). Scenes restricted to confirmed shapes in
anim_engine.py. CTA is the final beat; do not append after it."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py")); ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)
IMG = str(HERE / "build/img/backoffice") + "/"
CACHE = HERE / "build/cuthours"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = HERE / "build/cuthours_body.mp4"
def P(n): return IMG + n + ".jpg"

B = [
  # --- A. The problem (question ladder, rung 1) ---
  {"vo": "Here's the question every busy HVAC, plumbing, or electrical shop owner asks eventually: why does the back office get worse the busier the shop gets?",
   "scene": "split_photo", "c": {"photo": P("before_stress"), "eyebrow": "The busy-shop wall", "title": "Trucks roll, the office drowns", "sub": "Chasing invoices, building spreadsheets, after hours"}},
  {"vo": "Because the paperwork scales with every truck you add, but the office headcount usually doesn't. Someone is staying late to chase invoices, build a cash spreadsheet by hand, and re-price the pricebook item by item.",
   "scene": "split_photo", "c": {"photo": P("bolton_mess"), "eyebrow": "Why it piles up", "title": "Paperwork scales with trucks", "sub": "Headcount usually doesn't"}},
  {"vo": "So what's the usual fix? Hire another office person. That adds a full salary and benefits, and it only buys you a few months before the same wall shows up again.",
   "scene": "split_photo", "c": {"photo": P("backoffice_pile"), "eyebrow": "The usual fix", "title": "Another desk, another salary", "sub": "There is a cheaper way that adds none"}},

  {"vo": "So how does AI actually cut those hours without hiring anyone? Here's how it works.", "scene": "chapter", "c": {"num": "01", "title": "How it works"}},

  # --- B. The install + all eight agents ---
  {"vo": "Top Builder AI is eight self-learning agents that install on top of the ServiceTitan and QuickBooks you already run. They don't replace them. They run the back office those tools were never built to automate.",
   "scene": "split_photo", "c": {"photo": P("command_center"), "eyebrow": "What it is", "title": "Eight agents on top of your stack", "sub": "ServiceTitan and QuickBooks stay. The back office runs."}},
  {"vo": "Two of the eight sit at the front of the phone and the truck. Booking answers calls nights and weekends, screens the job, and puts it straight on the calendar instead of losing it to voicemail.",
   "scene": "split_photo", "c": {"photo": P("frontoffice"), "eyebrow": "Agent · Booking 24/7", "title": "Booking answers after hours", "sub": "Screens the job. Books it. Nothing goes to voicemail."}},
  {"vo": "Routing and Dispatch assigns the next job by drive time and margin together, not just whichever truck is closest, so a tech doesn't burn an hour driving to a low-margin call.",
   "scene": "split_photo", "c": {"photo": P("handshake"), "eyebrow": "Agent · Routing & Dispatch", "title": "Routing weighs drive time AND margin", "sub": "Not just 'which truck is closest'"}},
  {"vo": "The Financial agent is the one running the numbers in the background. It projects your thirty, sixty, and ninety day cash position, and flags a job that's on track to lose money before it closes, not after.",
   "scene": "split_photo", "c": {"photo": P("margin_leak"), "eyebrow": "Agent · Financial", "title": "Financial projects your cash", "sub": "30, 60, and 90 day cash. Losing jobs, flagged early."}},
  {"vo": "The Collections agent works your accounts-receivable aging list around the clock and drafts the dunning emails and texts for you to approve, so past-due invoices stop sitting untouched for weeks.",
   "scene": "split_photo", "c": {"photo": P("agent_review"), "eyebrow": "Agent · Collections", "title": "Collections works the aging list", "sub": "Drafts the emails and texts. You approve and send."}},
  {"vo": "Inventory and Workforce cover materials and people. Inventory finds unbilled materials and catches shrinkage before it disappears into a job that never got charged for it. Workforce forecasts overtime before the week happens, not on the Friday paycheck.",
   "scene": "cards", "c": {"title": "Materials and people", "items": [
     ("\U0001F4E6", "Inventory · unbilled materials, shrinkage"),
     ("\U0001F465", "Workforce · overtime before the week")]}},
  {"vo": "Documents and Pricebook cover the paperwork you'd otherwise do at ten at night. Documents files bills, warranties, and certificates of insurance as they land. Pricebook re-prices items the moment a vendor cost changes, so your margin doesn't quietly erode.",
   "scene": "cards", "c": {"title": "Paperwork and pricing", "items": [
     ("\U0001F4C4", "Documents · files bills, warranties, COIs"),
     ("\U0001F3F7️", "Pricebook · re-prices on vendor cost changes")]}},

  # --- C. Augment, not replace ---
  {"vo": "Now, will the AI replace your office staff, or work alongside them? Here's the honest part.",
   "scene": "chapter", "c": {"num": "02", "title": "Augment, not replace"}},
  {"vo": "These agents augment your team. They do not run your shop unattended, and they were never built to.",
   "scene": "split_photo", "c": {"photo": P("team"), "eyebrow": "Augment, not replace", "title": "Your team stays in the seat", "sub": "The agents do the hours nobody wants"}},
  {"vo": "So is it actually safe to let AI touch your accounting numbers? By default, every agent only advises. It proposes, a person approves, every executed action is reversible, and everything is logged.",
   "scene": "secure", "c": {"title": "The human stays in the loop", "items": [
     ("✅", "Advisory by default", "Every agent proposes; a person approves"),
     ("↩", "Reversible", "Every executed action has an undo"),
     ("\U0001F4DD", "Logged", "Every recommendation and approval is audited")]}},
  {"vo": "And every dollar and hour is computed by tested code, not guessed by the AI, so the numbers are exact and auditable. The AI explains the math. It never makes it up.",
   "scene": "split_photo", "c": {"photo": P("hero"), "eyebrow": "Computed, not guessed", "title": "The AI explains the math", "sub": "It never makes it up. The figures are auditable."}},

  # --- D. Install, day-to-day, and the honest fit question ---
  {"vo": "How does it actually connect to the ServiceTitan and QuickBooks you already run? Install takes days, not months, through the integrations you already have, and your data stays isolated to your shop.",
   "scene": "split_photo", "c": {"photo": P("team"), "eyebrow": "The install", "title": "Days, not months", "sub": "Through your existing integrations. Data isolated per shop."}},
  {"vo": "So what does an AI-run back office actually look like, day to day? If your front office hums on ServiceTitan but the back office runs on late nights and spreadsheets, this gives those hours back without putting another person on payroll.",
   "scene": "before_after", "c": {"before": P("before_stress"), "after": P("after_calm"), "caption": "Late nights and spreadsheets -> hours given back"}},
  {"vo": "Is this the right move for your shop? It's built for a multi-crew shop that's already busy and drowning in the office work that comes with growth, not a one-truck operation that's still figuring out its first hire.",
   "scene": "split_photo", "c": {"photo": P("frontoffice"), "eyebrow": "Is this you?", "title": "Built for the busy, growing shop", "sub": "Drowning in office work that comes with more trucks"}},
  {"vo": "Book a fit call and watch it run against your own data. Onboarding is hands-on, in a small quarterly cohort, with a thirty-day board-ready-or-free guarantee.",
   "scene": "cta", "c": {"eyebrow": "Top Builder AI · for ServiceTitan contractors", "title": "Get those hours back, no new hire", "sub": "Book a fit call and watch it run on your own data", "url": "topbuilderai.com/demo.html"}},
]

if __name__ == "__main__":
    secs = ae.render_body(B, str(OUT), CACHE, voice="blend")
    print(f"BODY {secs:.1f}s ({secs/60:.1f} min), {len(B)} beats -> {OUT}")
