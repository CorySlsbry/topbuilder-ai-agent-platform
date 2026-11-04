"""ServiceTitan -> QuickBooks AUTOMATED JOB COSTING video BODY — from
landing/_content/blog-1-connect-servicetitan-quickbooks-automated-job-costing.md (its Companion video
script). Reuses the backoffice image set (no new image-gen). Scenes restricted to confirmed shapes in
anim_engine.py. CTA is the final beat; do not append after it."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py")); ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)
IMG = str(HERE / "build/img/backoffice") + "/"
CACHE = HERE / "build/jobcosting"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = HERE / "build/jobcosting_body.mp4"
def P(n): return IMG + n + ".jpg"

B = [
  # --- A. The frustration ---
  {"vo": "If you run ServiceTitan and QuickBooks, you already know the frustration. Your company P and L looks fine, but ask which jobs actually made money and the answer is a guess.",
   "scene": "split_photo", "c": {"photo": P("before_stress"), "eyebrow": "The frustration", "title": "Which jobs actually made money?", "sub": "The P and L looks fine. The job profit is a guess."}},
  {"vo": "Here is why, and how to fix it.", "scene": "chapter", "c": {"num": "01", "title": "Why job costing breaks"}},

  # --- B. What the native sync does ---
  {"vo": "ServiceTitan's built-in QuickBooks integration does a real job. It syncs your invoices, your payments, and your customers into QuickBooks. Turn that on first.",
   "scene": "cards", "c": {"title": "What the native sync does", "items": [
     ("\U0001F4C4", "Invoices into QuickBooks"), ("\U0001F4B5", "Payments into QuickBooks"),
     ("\U0001F465", "Customers into QuickBooks")]}},
  {"vo": "But here is the gap. That sync moves money. It does not put your field costs on the right job. Your technician hours sit in timesheets. Your material costs ride on purchase orders.",
   "scene": "split_photo", "c": {"photo": P("margin_leak"), "eyebrow": "The gap", "title": "The sync moves money, not cost", "sub": "Labor sits in timesheets. Materials ride on POs."}},
  {"vo": "And neither one automatically lands against the job that earned it. So the invoice syncs clean, and the job profit stays a mystery.",
   "scene": "split_photo", "c": {"photo": P("backoffice_pile"), "eyebrow": "The result", "title": "The invoice syncs, the profit hides", "sub": "Costs float away from the job that earned them"}},

  # --- C. The three numbers ---
  {"vo": "Real job costing needs three numbers to line up on the same job. Revenue from the invoice, labor from the timesheet, and materials from the purchase order.",
   "scene": "process", "c": {"title": "Three numbers, one job", "steps": [
     "Revenue from the invoice", "Labor from the timesheet", "Materials from the purchase order"]}},
  {"vo": "When any one of those floats into a general expense account, the profit number is wrong. That is the break, and it happens before the sync, not during it.",
   "scene": "split_photo", "c": {"photo": P("bolton_mess"), "eyebrow": "Where it breaks", "title": "One stray line breaks the math", "sub": "A cost in the wrong account, and profit is wrong"}},

  # --- D. The bridge ---
  {"vo": "The fix is a bridge in the middle. Field data comes out of ServiceTitan. The bridge categorizes it, costs it to the right job, and reconciles it.",
   "scene": "chapter", "c": {"num": "02", "title": "The integration bridge"}},
  {"vo": "Then clean, job-coded entries land in QuickBooks as financial truth. That is exactly what Top Builder AI does. It installs on top of the ServiceTitan and QuickBooks you already run. It does not replace either one.",
   "scene": "split_photo", "c": {"photo": P("command_center"), "eyebrow": "Field data into financial truth", "title": "Categorize, cost, reconcile", "sub": "Clean job-coded entries into QuickBooks"}},
  {"vo": "A Financial agent handles the money. An Inventory agent handles the materials. Together they cost the labor and materials against the job that consumed them.",
   "scene": "cards", "c": {"title": "Two agents do the work", "items": [
     ("\U0001F4B0", "Financial agent · the money"), ("\U0001F4E6", "Inventory agent · the materials")]}},

  # --- E. The firewall ---
  {"vo": "And here is the part that matters most in accounting. Every dollar and hour is computed by tested code. The AI only explains it. It cannot change a number. It cannot hallucinate a cost.",
   "scene": "secure", "c": {"title": "The numbers are computed, not guessed", "items": [
     ("\U0001F512", "Tested code", "Every dollar and hour computed by pure code"),
     ("\U0001F4AC", "AI explains only", "It narrates the figure, never changes it"),
     ("\U0001F50D", "Auditable", "The same inputs always make the same number")]}},
  {"vo": "You stay in control too. Every agent runs Off, Approve-first, or Auto, with full undo and a complete audit trail. Your data is isolated and encrypted, and it never trains another shop's system.",
   "scene": "split_photo", "c": {"photo": P("agent_review"), "eyebrow": "You stay in control", "title": "Off, Approve-first, or Auto", "sub": "Full undo and audit. Your data stays yours."}},

  # --- F. Close ---
  {"vo": "You keep ServiceTitan. You keep QuickBooks. You just add the layer that makes them tell the truth about your jobs.",
   "scene": "before_after", "c": {"before": P("before_stress"), "after": P("after_calm"), "caption": "Job profit is a guess -> job profit you can defend"}},
  {"vo": "If you would like to see it run against your own setup, book a quick fit call and we will walk through it together. The install is hands-on, runs in a small quarterly cohort, with a thirty-day board-ready-or-free guarantee.",
   "scene": "cta", "c": {"eyebrow": "Top Builder AI · for ServiceTitan contractors", "title": "See the truth about your jobs", "sub": "Book a fit call, board-ready-or-free in 30 days", "url": "topbuilderai.com/demo.html"}},
]

if __name__ == "__main__":
    secs = ae.render_body(B, str(OUT), CACHE, voice="blend")
    print(f"BODY {secs:.1f}s ({secs/60:.1f} min), {len(B)} beats -> {OUT}")
