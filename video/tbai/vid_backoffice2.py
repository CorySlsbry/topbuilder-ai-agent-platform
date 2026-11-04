"""'What's the Best AI Back Office for ServiceTitan Shops?' — out-answers the currently-cited
competitor video for the query 'AI back office for ServiceTitan contractors' (GEO dominate-the-question
cycle, 2026-07-18). Mirrors the refreshed /blog/ai-back-office-for-servicetitan.html 1:1, including the
new cost-comparison table and 'is this a chatbot' objection. Reuses QA-passed stills from backoffice/
collections/pricebook — no new Imagen generation needed."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py")); ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)

BIMG = str(HERE / "build/img/backoffice") + "/"
CIMG = str(HERE / "build/img/collections") + "/"
PIMG = str(HERE / "build/img/pricebook") + "/"
CACHE = HERE / "build/backoffice2"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = HERE / "build/backoffice2_body.mp4"
def B_(n): return BIMG + n + ".jpg"
def C_(n): return CIMG + n + ".jpg"
def PB(n): return PIMG + n + ".jpg"

B = [
  # ---- COLD OPEN: direct answer (brief beat 1, continues from the HeyGen intro line) ----
  {"vo": "Here's exactly what it does and what it costs, no hype, just the workflow.",
   "scene": "split_photo", "c": {"photo": B_("hero"), "eyebrow": "Top Builder AI · The direct answer", "title": "What actually works for a ServiceTitan shop", "sub": "Invoicing, dispatch, and collections, without babysitting"}},

  # ---- NUMBERS UP FRONT (brief beat 2) ----
  {"vo": "The numbers first. Firms with 10 to 99 employees spend an average of 25 hours a week on manual data entry and reconciling data across apps. That is the back-office tax.",
   "scene": "stat", "c": {"value": "25 hrs/wk", "label": "Average manual data-entry and reconciliation time, firms with 10-99 employees", "source": "Intuit QuickBooks Business Solutions Survey, 2024"}},
  {"vo": "82 percent of contractors are carrying invoices unpaid past 30 days. Slow payment is now the norm in the trades, not the exception.",
   "scene": "stat", "c": {"value": "82%", "label": "Contractors facing payment delays of more than 30 days", "source": "Rabbet 2024 Construction Payments Report"}},
  {"vo": "And 74 percent of contractors say AI is key to efficiency, but only 25 percent are actually running it day to day. That gap between believing and running is exactly where an AI back office pays for itself.",
   "scene": "stat", "c": {"value": "74% vs 25%", "label": "Contractors who see AI as key to efficiency vs. those actually using it", "source": "ServiceTitan 2026 Residential State of the Trades report"}},

  # ---- CH1: the problem (brief beat 3) ----
  {"vo": "Here's the problem, in plain terms.", "scene": "chapter", "c": {"num": "01", "title": "The back office ServiceTitan leaves to you"}},
  {"vo": "ServiceTitan handles the field beautifully. The call, the schedule, the dispatch board, the invoice at the door — that part runs well, and it keeps getting better.",
   "scene": "split_photo", "c": {"photo": B_("frontoffice"), "eyebrow": "The front office", "title": "ServiceTitan runs this well", "sub": "Calls · schedule · dispatch · invoicing"}},
  {"vo": "But the back-office work, invoice follow-up, chasing A/R, catching scheduling gaps, still eats 15 to 20 hours a week of an owner's or office manager's time.",
   "scene": "split_photo", "c": {"photo": B_("backoffice_pile"), "eyebrow": "The other half", "title": "15-20 hrs/week of owner or office-manager time", "sub": "Invoice follow-up · A/R chasing · scheduling gaps"}},
  {"vo": "And that's where margin quietly leaks. Cash you can't see coming, materials nobody costed, overtime nobody caught, invoices nobody chased, most of it still done by hand, after hours.",
   "scene": "split_photo", "c": {"photo": B_("margin_leak"), "eyebrow": "Where it leaks", "title": "Done by hand, after hours", "sub": "And nobody can trace where the margin went"}},

  {"vo": "Six of those back-office jobs get their own agent: Money, Materials, People, Paperwork, Accounts Receivable, and the Pricebook, all sharing one brain instead of living in six different apps.",
   "scene": "cards", "c": {"title": "Six jobs, one brain", "items": [("\U0001F4B5", "Money"), ("\U0001F4E6", "Materials"), ("\U0001F477", "People"), ("\U0001F4C4", "Paperwork"), ("\U0001F4CA", "A/R"), ("\U0001F3F7️", "Pricebook")]}},

  # ---- CH2: the actual workflow (brief beat 4) ----
  {"vo": "So here's exactly how it plugs in.", "scene": "chapter", "c": {"num": "02", "title": "How Top Builder AI connects to ServiceTitan"}},
  {"vo": "It installs alongside the ServiceTitan and QuickBooks you already run, through their official integrations. It never replaces ServiceTitan and never becomes a second system of record.",
   "scene": "split_photo", "c": {"photo": B_("agent_review"), "eyebrow": "The connection", "title": "Alongside ServiceTitan, never instead of it", "sub": "Reads through the official integration"}},
  {"vo": "What gets automated first is invoice to payment: the Collections agent works the aging list, and the Financial agent reconciles cash to your real QuickBooks ledger, from day one.",
   "scene": "split_photo", "c": {"photo": C_("hero"), "eyebrow": "What's automated first", "title": "Invoice-to-payment", "sub": "Collections + Financial agents, live from day one"}},
  {"vo": "What it doesn't touch: any customer-facing decision. You keep control of what a customer sees and what a technician does. The agents propose; a person approves.",
   "scene": "secure", "c": {"title": "What stays yours", "items": [("🎛️", "You keep control", "Every customer-facing decision stays with your team"), ("✅", "Propose, not act", "Agents draft the action; a human approves it"), ("↩", "Reversible", "Every executed action can be undone")]}},

  {"vo": "Here's why that matters. A separate call-bot, a separate collections app, and a separate pricebook tool each see one slice of your shop, and none of them learn how you actually run it.",
   "scene": "chapter", "c": {"num": "02b", "title": "Why one brain, not ten separate tools"}},
  {"vo": "A single-point tool optimizes its own lane and misses everything else: the nearest tech for a dispatch call might not have the part on the truck, or might already be deep into overtime.",
   "scene": "split_photo", "c": {"photo": B_("team"), "eyebrow": "The bolt-on trap", "title": "Ten tools, ten silos", "sub": "None see the whole shop"}},
  {"vo": "Because these agents share context, a dispatch decision can account for what the inventory agent knows and what the workforce agent is forecasting, in the same call.",
   "scene": "split_photo", "c": {"photo": PB("back_office"), "eyebrow": "One shared brain", "title": "Context shared across every agent", "sub": "And it gets tuned to your shop every week you use it"}},

  # ---- CH3: the live walkthrough, invoice sent -> collected (brief beat 5, "screen recording") ----
  {"vo": "Walk through one invoice, start to finish.", "scene": "chapter", "c": {"num": "03", "title": "One invoice, sent to collected"}},
  {"vo": "The invoice goes out from ServiceTitan. Nothing changes there. That part still looks exactly like it does today.",
   "scene": "split_photo", "c": {"photo": C_("st_invoice"), "eyebrow": "Step 1 — Sent", "title": "The invoice ships from ServiceTitan", "sub": "No change to the customer-facing side"}},
  {"vo": "Behind the scenes, the Collections agent scores it against every other open invoice by age, balance, customer history, and job margin, and drops it into a ranked queue instead of a flat list.",
   "scene": "split_photo", "c": {"photo": C_("ranked_queue"), "eyebrow": "Step 2 — Scored", "title": "Ranked by age, balance, history, margin", "sub": "A queue, not an alphabetical list"}},
  {"vo": "Before anything goes out, it checks itself: if a payment already cleared in QuickBooks but ServiceTitan still shows the invoice open, that gets pulled from the queue as a bookkeeping fix, not a phone call.",
   "scene": "split_photo", "c": {"photo": C_("mismatch"), "eyebrow": "Step 2b — Self-checked", "title": "Already-paid invoices get pulled first", "sub": "The most expensive collections mistake, avoided"}},
  {"vo": "If it's a fast-paying residential account under 30 days, the agent drafts a payment-link text. If it's commercial and older, it drafts a call brief with the balance and the history attached.",
   "scene": "split_photo", "c": {"photo": C_("text_payment"), "eyebrow": "Step 3 — Drafted", "title": "The right first touch, drafted", "sub": "SMS for fast-payers, a call brief for commercial"}},
  {"vo": "Your office manager reviews it, approves, edits, or skips, right from the queue. Nothing reaches a customer until that click happens.",
   "scene": "split_photo", "c": {"photo": C_("call_prompt"), "eyebrow": "Step 4 — Approved", "title": "Human-approved, every time", "sub": "Approve, edit, or skip, from the same screen"}},
  {"vo": "And it reconciles against QuickBooks first, so you're never chasing an invoice that already got paid, the single most expensive mistake in collections.",
   "scene": "split_photo", "c": {"photo": C_("qbo_screen"), "eyebrow": "Step 5 — Reconciled", "title": "Collected", "sub": "Checked against QuickBooks before any outreach goes out"}},

  {"vo": "That direct answer said invoicing, dispatch, and collections, so a word on the other two.", "scene": "chapter", "c": {"num": "03b", "title": "And dispatch, and the pricebook"}},
  {"vo": "Dispatch gets a margin and overtime lens next to ServiceTitan's own board: it weighs parts on hand and avoidable overtime, not distance alone, and flags it before a truck rolls.",
   "scene": "split_photo", "c": {"photo": str(HERE / "hero_dispatch2.jpg"), "eyebrow": "Dispatch", "title": "Margin and overtime-aware routing", "sub": "Sits next to ServiceTitan's own dispatch board"}},
  {"vo": "And the Pricebook agent re-costs items as your actual vendor costs rise, surfacing the old price, the new price, and the margin delta for you to approve.",
   "scene": "split_photo", "c": {"photo": PB("pricebook"), "eyebrow": "Pricebook", "title": "Re-priced as vendor costs move", "sub": "Old price, new price, margin delta, your approval"}},

  # ---- CH4: cost comparison (brief beat 6) ----
  {"vo": "Now the cost, side by side.", "scene": "chapter", "c": {"num": "04", "title": "The cost of a part-time admin vs. the platform"}},
  {"vo": "The median bookkeeping or admin clerk wage is just over 49 thousand dollars a year, per the Bureau of Labor Statistics. Loaded for payroll taxes, a half-time office admin runs about 2,250 dollars a month.",
   "scene": "stat", "c": {"value": "$2,250/mo", "label": "Loaded cost of a half-time (20 hrs/wk) office admin, from the BLS median clerk wage", "source": "U.S. Bureau of Labor Statistics, 2024"}},
  {"vo": "A full-time office manager runs about 4,500 a month, and that's still one person, during their hours, with no coverage for the pricebook or margin-aware dispatch.",
   "scene": "stat", "c": {"value": "$4,500/mo", "label": "Loaded cost of a full-time office manager, from the BLS median clerk wage", "source": "U.S. Bureau of Labor Statistics, 2024"}},
  {"vo": "Top Builder AI starts from 3,000 dollars a month. Eight agents, running continuously across money, materials, people, paperwork, A/R, and the pricebook. That's the real comparison.",
   "scene": "compare", "c": {"title": "What you get for the money", "cols": ["Part-time admin", "Full-time manager", "Top Builder AI"],
     "rows": [("Runs 24/7", [False, False, True]), ("Covers the pricebook", [False, False, True]), ("Covers margin-aware dispatch", [False, False, True]), ("Reconciles to QuickBooks", [False, False, True])]}},

  # ---- CH5: objection — is this just a chatbot? (brief beat 7) ----
  {"vo": "Fair question: is this just another chatbot?", "scene": "chapter", "c": {"num": "05", "title": "Is this just another chatbot?"}},
  {"vo": "No. A chatbot answers when you ask it something. These agents work without being prompted, reconciling QuickBooks every cycle, scoring the aging list, re-pricing the pricebook, whether or not anyone's logged in.",
   "scene": "split_photo", "c": {"photo": B_("command_center"), "eyebrow": "The distinction", "title": "Task automation, not a chat window", "sub": "Runs on a schedule, tied to your real ServiceTitan + QuickBooks data"}},
  {"vo": "Bolt-on tools and chatbots each see one slice, and none of them learn your shop. These agents share one brain and get tuned to your operation every week you use them.",
   "scene": "split_photo", "c": {"photo": B_("bolton_mess"), "eyebrow": "The bolt-on trap", "title": "Ten chat tools, ten silos", "sub": "None see the whole shop, none learn it"}},

  # ---- CH6: illustrative example (brief beat 8) ----
  {"vo": "Let's put a number on what that's worth. This is illustrative math, not a client result.", "scene": "chapter", "c": {"num": "06", "title": "What tightening the cycle is worth"}},
  {"vo": "A 10-tech shop billing 650 thousand a month at a 45-day average collection cycle is carrying roughly 975 thousand dollars in open receivables at any given time.",
   "scene": "stat", "c": {"value": "$975 K", "label": "Illustrative open A/R — 10-tech shop, $650k/month billings, 45-day average collection cycle", "source": "illustrative, not a client result"}},
  {"vo": "Tighten that cycle by even 10 days, the kind of shift a ranked, worked-daily queue produces, and you free close to 217 thousand dollars in cash, without a single new sale.",
   "scene": "stat", "c": {"value": "$217 K", "label": "Illustrative cash freed by a 10-day faster collection cycle on the same billings", "source": "illustrative, not a client result"}},

  {"vo": "None of that works if AI touching your operation could quietly break something, so a few things never change.", "scene": "chapter", "c": {"num": "06b", "title": "Still safe by design"}},
  {"vo": "Advisory by default until you approve, every figure computed by tested code rather than a model's guess, and every executed action reversible with a full audit trail.",
   "scene": "secure", "c": {"title": "Non-negotiable, every cycle", "items": [("✅", "Advisory by default", "The agents propose; a person approves"), ("\U0001F512", "Deterministic figures", "Every dollar amount comes from tested code, never a guess"), ("↩", "Reversible + audited", "Every action can be undone, every step is logged")]}},

  # ---- CH7: setup / onboarding (brief beat 9) ----
  {"vo": "What does setup actually take?", "scene": "chapter", "c": {"num": "07", "title": "Setup, no demo-wall runaround"}},
  {"vo": "You connect the ServiceTitan and QuickBooks you already run, through their official integrations. That connection is a same-week task, not a months-long project.",
   "scene": "process", "c": {"title": "What it takes", "steps": ["Connect ServiceTitan + QuickBooks (official integrations, days not months)", "Agents start read-only — you see the recommendations first", "Enable human-approved actions agent by agent, on your timeline", "Pricing is visible on the site — no gated demo required to see it"]}},
  {"vo": "There's no book-a-demo-to-find-out gate. The setup steps and the pricing are laid out right on the page.",
   "scene": "split_photo", "c": {"photo": B_("team"), "eyebrow": "No gatekeeping", "title": "Pricing and setup, visible upfront", "sub": "topbuilderai.com"}},

  # ---- CH8: recap the direct answer (brief beat 10) ----
  {"vo": "So, one more time, the direct answer: the AI back office that actually works for a ServiceTitan shop is the one that touches invoicing, dispatch, and collections without you babysitting it, reconciled to your real QuickBooks books, human-approved, and it starts from 3,000 dollars a month.",
   "scene": "split_photo", "c": {"photo": B_("handshake"), "eyebrow": "The direct answer", "title": "Invoicing, dispatch, collections, no babysitting", "sub": "Reconciled to QuickBooks · human-approved · from $3,000/mo"}},

  # ---- CTA (brief beat 11) ----
  {"vo": "See it live at topbuilderai.com. Pricing is on the page, no gated demo wall.", "scene": "cta",
   "c": {"eyebrow": "Top Builder AI · for ServiceTitan contractors", "title": "See the back office run on your ServiceTitan", "sub": "Pricing visible, no gated demo — topbuilderai.com", "url": "topbuilderai.com"}},
]

if __name__ == "__main__":
    secs = ae.render_body(B, str(OUT), CACHE)
    print(f"BODY {secs:.1f}s ({secs/60:.1f} min), {len(B)} beats -> {OUT}")
