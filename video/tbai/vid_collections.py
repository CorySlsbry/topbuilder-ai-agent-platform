"""Collections / A/R aging video BODY — mirrors /blog/servicetitan-ar-collections-automation.html (GEO 1:1)."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)

IMG = str(HERE / "build/img/collections") + "/"
PIMG = str(HERE / "build/img/pricebook") + "/"  # pricebook images for substitution
CACHE = HERE / "build/collections"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = HERE / "build/collections_body.mp4"
def P(n): return IMG + n + ".jpg"
def PP(n): return PIMG + n + ".jpg"  # pricebook substitutes (already QA-passed)

B = [
  # ---- HOOK ----
  {"vo": "If you run a trades shop on ServiceTitan, your aging report probably has more outstanding invoices in it right now than you want to admit.",
   "scene": "photo", "c": {"photo": P("hero"), "eyebrow": "Top Builder AI · Collections", "title": "The A/R problem every shop has", "sub": "The invoice was sent. The cash isn't here."}},
  {"vo": "The board shows $700k billed last month. The bank account doesn't reflect it. The invoices are there — they just haven't been collected.",
   "scene": "split_photo", "c": {"photo": P("cash_worry"), "eyebrow": "The cash gap", "title": "Billed revenue vs. collected cash", "sub": "The difference lives in the A/R column"}},
  {"vo": "A shop doing 700 thousand a month at a 45-day average collection cycle is carrying over a million dollars in outstanding receivables at any point. That's illustrative, but most shops are close.",
   "scene": "stat", "c": {"value": "$1.05 M", "label": "Illustrative open A/R for a $700k/month shop at 45-day average collection cycle", "source": "illustrative"}},
  {"vo": "The problem isn't bad customers. It's that nobody has a prioritized, ready-to-contact queue — just an aging report that lists everything the same way.",
   "scene": "split_photo", "c": {"photo": P("cash_worry"), "eyebrow": "The real bottleneck", "title": "A list — not a queue", "sub": "Oldest first isn't always right"}},

  # ---- CH1: why the list isn't enough ----
  {"vo": "Here's why the aging report alone doesn't solve the problem.", "scene": "chapter", "c": {"num": "01", "title": "The aging report is a list, not a plan"}},
  {"vo": "ServiceTitan has solid invoicing infrastructure. You can email invoices from the truck, collect payment online, and see the aging buckets. That infrastructure is real and useful.",
   "scene": "split_photo", "c": {"photo": P("hero"), "eyebrow": "ServiceTitan A/R", "title": "Good infrastructure", "sub": "Invoicing, online payment, aging report"}},
  {"vo": "But it doesn't prioritize. Every invoice in the 31-to-60 bucket looks the same — whether it's a $300 tune-up or a $14,000 commercial install on a relationship that took three years to build.",
   "scene": "split_photo", "c": {"photo": P("ranked_queue"), "eyebrow": "The gap", "title": "All invoices look equal", "sub": "The aging report doesn't rank them"}},
  {"vo": "And it doesn't reconcile against QuickBooks in real time. A payment deposited in QBO may not have cleared the ServiceTitan invoice yet — so the aging report says open when the money's already in the bank.",
   "scene": "split_photo", "c": {"photo": P("mismatch"), "eyebrow": "The reconciliation gap", "title": "ST and QuickBooks don't always agree", "sub": "Chasing a paid invoice damages goodwill"}},

  # ---- CH2: the reconciliation problem ----
  {"vo": "That reconciliation problem is worth dwelling on, because it's the most expensive mistake in collections.", "scene": "chapter", "c": {"num": "02", "title": "The QuickBooks reconciliation gap"}},
  {"vo": "A check arrives. It gets deposited in QuickBooks. But in ServiceTitan, the invoice is still showing open because the payment wasn't linked to the specific job.",
   "scene": "split_photo", "c": {"photo": P("qbo_screen"), "eyebrow": "How it happens", "title": "Deposited — but not applied", "sub": "ServiceTitan still shows the invoice open"}},
  {"vo": "Now your office calls a customer who already paid. That call costs goodwill. If it happens twice with the same account, it costs the relationship.",
   "scene": "split_photo", "c": {"photo": P("mismatch"), "eyebrow": "The consequence", "title": "Calling customers who already paid", "sub": "Goodwill is hard to rebuild"}},
  {"vo": "Three causes make this common: unapplied payments, credits entered in one system not the other, and multi-invoice commercial checks applied to a general balance rather than specific jobs.",
   "scene": "process", "c": {"title": "Three ways invoices go stale", "steps": ["Unapplied payment: deposited in QBO, not linked in ServiceTitan", "Credit or adjustment entered in one system only", "Multi-invoice commercial check applied to general AR balance"]}},
  {"vo": "The Financial agent reconciles both ledgers at the start of every cycle. It finds the mismatches, removes them from the chase queue, and routes them to the bookkeeper as cleanup tasks.",
   "scene": "stat", "c": {"value": "Mismatch first", "label": "Reconciliation mismatches removed before any outreach is proposed — they're bookkeeping tasks, not collection calls", "source": "every cycle"}},

  # ---- CH3: the four-step loop ----
  {"vo": "Here's the full collections loop the Financial agent runs.", "scene": "chapter", "c": {"num": "03", "title": "The four-step Financial agent loop"}},
  {"vo": "Step one: ingest the open-invoice report from ServiceTitan. Invoice number, balance, customer, job type, technician, date, last payment event, and any associated dispute notes.",
   "scene": "process", "c": {"title": "Step 1 — Ingest ServiceTitan", "steps": ["Invoice number, balance, customer", "Job type, technician, invoice date", "Last payment event", "Associated callback tasks and dispute notes"]}},
  {"vo": "Step two: cross-reference against QuickBooks. Pull the QBO accounts receivable balance for each customer, flag any mismatch, and remove those from the chase queue.",
   "scene": "split_photo", "c": {"photo": P("mismatch"), "eyebrow": "Step 2 — Reconcile", "title": "Compare ST to QuickBooks", "sub": "Mismatches go to the bookkeeper, not the caller"}},
  {"vo": "Step three: score and rank the genuine open invoices. Four factors: age, balance, customer payment history, and job margin. The output is a ranked queue, not an alphabetical list.",
   "scene": "process", "c": {"title": "Step 3 — Score and rank", "steps": ["Age: older invoices weight more heavily", "Balance: larger balances mean more gross profit at risk", "Customer history: payment patterns per account", "Job margin: a high-margin job uncollected is a bigger loss"]}},
  {"vo": "Step four: propose the contact queue for the office manager to review. The manager sees each invoice, the recommended action, and the reason — then approves, edits, or skips each one.",
   "scene": "split_photo", "c": {"photo": P("ranked_queue"), "eyebrow": "Step 4 — Human approval", "title": "Proposed. Not automatic.", "sub": "Nothing reaches a customer without approval"}},

  # ---- CH4: the scoring model ----
  {"vo": "Let's go deeper on the scoring model.", "scene": "chapter", "c": {"num": "04", "title": "How the prioritization model works"}},
  {"vo": "Age matters because recovery probability drops with time. The risk acceleration is steeper past 60 days — it's not linear.",
   "scene": "stat", "c": {"value": "Age", "label": "The probability of full collection drops as invoices age past 60 days — weighted more steeply than the 0-to-30 bucket", "source": "scoring model"}},
  {"vo": "Balance matters because larger invoices represent more gross profit dollars sitting uncollected. A $9,200 invoice at 42 days outranks a $280 tune-up at 58 days for the same daily contact budget.",
   "scene": "stat", "c": {"value": "Balance", "label": "Larger balances get proportionally more weight — a $9,200 invoice at 42 days outranks a $280 invoice at 58 days", "source": "scoring model"}},
  {"vo": "Customer history matters because it tells you the right first touch. A customer who has always paid after one SMS needs a different opening than one who requires a direct call every time.",
   "scene": "split_photo", "c": {"photo": P("call_prompt"), "eyebrow": "Customer history", "title": "The right contact type", "sub": "SMS for fast-payers; calls for commercial accounts"}},
  {"vo": "And job margin matters because a 58% gross-margin install uncollected is a bigger financial hit than a thin-margin equipment swap at the same dollar amount.",
   "scene": "stat", "c": {"value": "Margin", "label": "A $6,000 install at 58% margin is a larger cash exposure than an $8,000 job at 18% — the scoring reflects that", "source": "scoring model"}},

  # ---- CH5: the contact types ----
  {"vo": "For each ranked invoice, the agent proposes a specific action type.", "scene": "chapter", "c": {"num": "05", "title": "Three types of proposed actions"}},
  {"vo": "First touch for residential customers under 30 days: a payment-link SMS. It's the fastest, least intrusive path. Most residential customers who just got busy pay within 24 hours of a text with a direct payment link.",
   "scene": "split_photo", "c": {"photo": P("text_payment"), "eyebrow": "Residential, under 30 days", "title": "Payment-link SMS", "sub": "Fast, low-friction, high close rate"}},
  {"vo": "Commercial accounts at 60 days or longer: a call prompt with the invoice number, the balance, a note on their payment history, and a suggested opening line. The office person makes the call; the agent wrote the brief.",
   "scene": "split_photo", "c": {"photo": P("call_prompt"), "eyebrow": "Commercial, 60+ days", "title": "Call prompt with brief", "sub": "Invoice number, balance, history, opening line"}},
  {"vo": "90-plus day accounts above a configurable threshold: an escalation flag recommending a formal demand approach, with a note on any prior dispute that should be resolved first.",
   "scene": "split_photo", "c": {"photo": P("mismatch"), "eyebrow": "90+ days, above threshold", "title": "Escalation flag", "sub": "Formal demand recommendation + dispute check"}},
  {"vo": "Every one of those proposed actions goes through the office manager before anything reaches a customer. The agent has no visibility into relationship context — that's what the approval step is for.",
   "scene": "secure", "c": {"title": "Human in the loop, always", "items": [("✅", "Manager approves", "Every proposed contact requires a human decision first"), ("↩", "Editable", "Every draft message or call brief is editable before approval"), ("📋", "Logged", "Every approved action is logged with timestamp, approver, and outcome")]}},

  # ---- CH6: worked example ----
  {"vo": "Let's put real numbers on it. These are illustrative — not a client result.", "scene": "chapter", "c": {"num": "06", "title": "A worked example: one cycle"}},
  {"vo": "A 10-tech HVAC shop. $650,000 in monthly billings. Outstanding A/R at $920,000 — about 42 days of revenue. 61-to-90 bucket is $170,000.",
   "scene": "stat", "c": {"value": "$920 K", "label": "Illustrative open A/R — 10-tech HVAC shop, $650k/month billings, 42-day average collection cycle", "source": "illustrative"}},
  {"vo": "The reconciliation pass finds $42,000 in the 61-to-90 bucket is actually an unapplied QuickBooks payment — not a collection call, a bookkeeping fix. That $42,000 comes out of the chase queue.",
   "scene": "stat", "c": {"value": "$42 K", "label": "Removed from the chase queue after reconciliation — unapplied QBO payment across 3 commercial invoices. Bookkeeper task.", "source": "illustrative"}},
  {"vo": "The scored queue for genuine 60-plus open invoices is now $128,000. The agent proposes 3 actions today.",
   "scene": "split_photo", "c": {"photo": P("ranked_queue"), "eyebrow": "After reconciliation", "title": "$128k in genuine open invoices", "sub": "3 proposed actions today"}},
  {"vo": "One: a payment-link text to a residential customer at 68 days, $3,840 balance. Payment history shows they've paid 4 of 5 similar invoices within 24 hours of an SMS.",
   "scene": "split_photo", "c": {"photo": P("text_payment"), "eyebrow": "Action 1 — Residential", "title": "$3,840 at 68 days", "sub": "SMS with payment link — history says it closes fast"}},
  {"vo": "Two: a call prompt to a commercial property manager at 74 days, $18,400 balance. Agent recommends a voice call with the invoice number and a note that the contact for this account recently changed.",
   "scene": "split_photo", "c": {"photo": P("call_prompt"), "eyebrow": "Action 2 — Commercial", "title": "$18,400 at 74 days", "sub": "Call prompt — new contact at the account"}},
  {"vo": "Three: an escalation flag on a 97-day account with a $61,000 balance. Above the shop's threshold. Agent recommends a formal demand approach and flags a dispute on one of the invoices that needs resolution first.",
   "scene": "split_photo", "c": {"photo": P("escalation"), "eyebrow": "Action 3 — Escalation", "title": "$61,000 at 97 days", "sub": "Above threshold — formal demand recommended"}},
  {"vo": "The office manager approves the first two, edits the call brief on action two to reference the correct job, and skips action three to discuss with the owner. Total time: about 8 minutes.",
   "scene": "stat", "c": {"value": "8 min", "label": "Office manager review time for 3 proposed actions — approved, edited, and one skipped for owner discussion", "source": "illustrative"}},

  # ---- CH7: before/after ----
  {"vo": "That's the shift.", "scene": "chapter", "c": {"num": "07", "title": "Before and after"}},
  {"vo": "Before: every morning starts with someone pulling two reports, trying to reconcile them manually, and deciding who to call based on gut feel and whoever is in the 90-day bucket.",
   "scene": "photo", "c": {"photo": PP("before_stress"), "eyebrow": "Before", "title": "Manual triage every morning", "sub": "Two reports. Gut feel. Oldest first."}},
  {"vo": "After: the queue is ranked and ready. The reconciliation is done. The three calls to make today are already briefed. Office manager reviews in minutes.",
   "scene": "photo", "c": {"photo": P("after_clear"), "eyebrow": "After", "title": "A ranked, ready-to-act queue", "sub": "Reconciled. Prioritized. Briefed."}},
  {"vo": "The outstanding A/R doesn't disappear overnight — but the 60-plus bucket shrinks consistently because the follow-up actually happens, on the right invoices, in the right order, every cycle.",
   "scene": "split_photo", "c": {"photo": P("handshake"), "eyebrow": "The outcome", "title": "Consistent follow-up on the right invoices", "sub": "The 60-plus bucket shrinks"}},

  # ---- CH8: safe and how it connects ----
  {"vo": "A few things that don't change, ever.", "scene": "chapter", "c": {"num": "08", "title": "Safe by design"}},
  {"vo": "No automated outreach. Every proposed contact requires the office manager to approve it first. The agent doesn't know about callbacks, disputes, or the relationship context the team holds.",
   "scene": "secure", "c": {"title": "Non-negotiable properties", "items": [("✅", "No auto-outreach", "Human-approved before any customer contact"), ("0️⃣", "No fabricated figures", "Every balance from deterministic code — the AI narrates, never invents"), ("↩", "Reversible", "Every write-back to ServiceTitan can be undone")]}},
  {"vo": "And the collections data feeds the cash-position report — cleared QBO cash plus expected collections from the scored queue — so you can answer the question a bank or CFO actually asks.",
   "scene": "stat", "c": {"value": "Cash position", "label": "Collections data feeds the board-ready cash forecast: cleared QBO cash + expected collections from the ranked queue", "source": "Financial agent"}},

  # ---- CTA ----
  {"vo": "If your aging report has invoices older than 60 days and your QuickBooks balance doesn't match what ServiceTitan says is open, those are the two signals the Financial agent addresses first.",
   "scene": "chapter", "c": {"num": "09", "title": "Your outstanding A/R is a solvable problem"}},
  {"vo": "Read the full playbook on the blog at topbuilderai.com — then book a 30-minute fit call and we'll run the reconciliation check against your actual books.",
   "scene": "cta", "c": {"eyebrow": "Top Builder AI · Financial Agent", "title": "Stop manually triaging the aging report", "sub": "Book a 30-minute fit call — topbuilderai.com/blog", "url": "topbuilderai.com/blog"}},
]

if __name__ == "__main__":
    secs = ae.render_body(B, str(OUT), CACHE)
    print(f"BODY {secs:.1f}s ({secs/60:.1f} min), {len(B)} beats -> {OUT}")
