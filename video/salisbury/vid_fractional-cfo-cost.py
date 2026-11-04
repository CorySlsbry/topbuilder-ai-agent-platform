"""Salisbury CFO long-form video BODY: "What does a fractional CFO cost for a construction company?"
Mirrors post_fractional-cfo-cost.html in the citation rhythm: open on the shallow question, answer it,
escalate one question per chapter, each with a cited stat/example + a takeaway. ~46 beats.

Structure overall = HeyGen avatar INTRO (build/intro.mp4) + this BODY + HeyGen avatar OUTRO
(build/outro.mp4), assembled by make_cfocost_video.py. Narration = cory-voice BLEND throughout.
Scenes restricted to confirmed shapes in anim_engine.py. CTA is the final body beat."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)
IMG = str(HERE / "build/img/cfocost") + "/"
CACHE = HERE / "build/cfocost"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = HERE / "build/cfocost_body.mp4"
def P(n): return IMG + n + ".jpg"

B = [
  # ---- A. Shallow question + answer-first ----
  {"vo": "What does a fractional CFO actually cost for a construction company? Let us answer it straight, with real numbers.",
   "scene": "title", "c": {"eyebrow": "Fractional CFO for construction", "title": "What does a fractional CFO cost?", "sub": "The honest 2026 number, by engagement type"}},
  {"vo": "Here is the short answer. For an ongoing retainer, expect about three thousand to nine thousand dollars a month.",
   "scene": "stat", "c": {"value": "$3K-$9K", "label": "Per month for an ongoing construction fractional CFO", "source": "nStar, CFO Advisors, Madras, The Cashflow CFO (2026)"}},
  {"vo": "A one-time diagnostic runs twenty-five hundred to ten thousand dollars. A fixed cleanup project runs five to fifteen thousand. The price follows the depth of the work, not the hours.",
   "scene": "split_photo", "c": {"photo": P("blueprints_desk"), "eyebrow": "Price follows the work", "title": "Three jobs, three prices", "sub": "A diagnostic, a sprint, and a retainer are not the same thing"}},

  # ---- B. Why so much cheaper than full-time ----
  {"vo": "The first deeper question. Why is fractional so much cheaper than hiring a CFO full time?",
   "scene": "chapter", "c": {"num": "01", "title": "Why fractional is cheaper"}},
  {"vo": "Because a full-time construction CFO costs a fortune. All in, that is about one hundred seventy thousand to three hundred sixty thousand dollars a year.",
   "scene": "stat", "c": {"value": "$170K-$360K", "label": "Full-time construction CFO, all-in, per year", "source": "CFMA 2025 compensation surveys"}},
  {"vo": "Smaller contractors pay a CFO around one hundred seventy-three thousand all in. Larger contractors push past three hundred fifty thousand. That is before recruiting, before the months a search takes, before the risk of a bad hire.",
   "scene": "split_photo", "c": {"photo": P("money_vs_seat"), "eyebrow": "The full-time price", "title": "A seat most contractors cannot fill", "sub": "Salary, bonus, benefits, payroll tax, and the search"}},
  {"vo": "Fractional shares one experienced person across several companies. A five thousand dollar a month retainer is sixty thousand a year, for the same caliber of judgment on the slice of time you need.",
   "scene": "compare", "c": {"title": "Full-time versus fractional", "cols": ["Fractional", "Full-time CFO"],
     "rows": [("CFO-level judgment", [True, True]), ("Six-figure salary", [False, True]),
              ("Months-long search", [False, True]), ("Sized to your real need", [True, False])]}},
  {"vo": "Most contractors doing one to twenty-five million do not have a quarter million dollars of CFO work every year. They have a few high-stakes decisions and a constant worry about cash.",
   "scene": "split_photo", "c": {"photo": P("owner_worry"), "eyebrow": "The real need", "title": "A few big calls, and the cash worry", "sub": "Fractional is sized to exactly that"}},

  # ---- C. What a CFO actually does ----
  {"vo": "Next question. What does a construction CFO actually do for that fee?",
   "scene": "chapter", "c": {"num": "02", "title": "What you are paying for"}},
  {"vo": "A bookkeeper records what already happened. A CFO tells you what it means and what to do next. The core work is job costing, work in progress, a cash forecast, and bank-ready reports.",
   "scene": "cards", "c": {"title": "The core deliverables", "items": [
     ("\U0001F4D0", "Job costing you can trust"), ("\U0001F4CA", "A WIP schedule"),
     ("\U0001F4C5", "A 13-week cash forecast"), ("\U0001F3E6", "Bank-ready statements")]}},
  {"vo": "Construction makes this hard. Money arrives in draws, held back by retainage. Costs land on jobs out of sync with billing. Profit is recognized over months, not when the check clears.",
   "scene": "split_photo", "c": {"photo": P("jobsite_frame"), "eyebrow": "Why it is hard", "title": "Contractor accounting is its own animal", "sub": "Draws, retainage, and percentage-of-completion"}},
  {"vo": "This is why the field has its own association, the C F M A. Contractor accounting does not look like normal accounting. A generalist CFO who has never managed work in progress will miss what sinks contractors.",
   "scene": "define", "c": {"eyebrow": "Topical authority", "term": "Why a specialist matters", "body": "CFMA exists because construction finance is different. Experience with WIP and job costing is not optional here."}},
  {"vo": "And the work includes the calls you cannot delegate to software. Take the big job that ties up cash, or two smaller ones that turn over faster? Buy the equipment, finance it, or rent it? Those are CFO judgments.",
   "scene": "split_photo", "c": {"photo": P("wip_paper"), "eyebrow": "The product is decisions", "title": "The reporting is table stakes", "sub": "The judgment calls are what you actually buy"}},

  # ---- D. Cost by engagement type (the data table) ----
  {"vo": "Now the detailed question. How much does each kind of engagement cost? The market has settled into three shapes.",
   "scene": "chapter", "c": {"num": "03", "title": "Cost by engagement"}},
  {"vo": "First, the diagnostic. A two to three week deep read of your books, job costing, and cash, ending in a written leak list. The market runs twenty-five hundred to ten thousand dollars.",
   "scene": "split_photo", "c": {"photo": P("xray_review"), "eyebrow": "Step one", "title": "The diagnostic", "sub": "A written leak list. $2,500 to $10,000 one-time."}},
  {"vo": "Second, the sprint. A fixed-scope cleanup and build-out. Fix the books, stand up job costing and work in progress, build the cash model. Five to fifteen thousand over six to eight weeks.",
   "scene": "split_photo", "c": {"photo": P("cash_forecast"), "eyebrow": "Step two", "title": "The sprint", "sub": "Fixed scope, $5,000 to $15,000, six to eight weeks"}},
  {"vo": "Third, the retainer. A monthly CFO seat. Forecasting, job-cost oversight, bank strategy, with the books handled inside the fee. Three to nine thousand a month for most contractors.",
   "scene": "split_photo", "c": {"photo": P("bank_meeting"), "eyebrow": "Step three", "title": "The retainer", "sub": "$3,000 to $9,000 a month, ongoing"}},
  {"vo": "Here is how the Salisbury CFO ladder lines up against the market. Every rung sits inside the published band. You pay for the work and the judgment, not a brand premium.",
   "scene": "compare", "c": {"title": "Salisbury CFO, at market on every rung", "cols": ["Salisbury", "Market"],
     "rows": [("X-Ray $3,500", [True, True]), ("Sprint $9.8K-$14.5K", [True, True]),
              ("Retainer $3.5K-$12K/mo", [True, True]), ("Books included", [True, False])]}},
  {"vo": "And a credible diagnostic is the right first step. The Expert CFO recommends exactly this path, diagnostic to pilot to retainer. Buy a small clear deliverable first, then decide on the bigger commitment with real information.",
   "scene": "process", "c": {"title": "The proven ladder", "steps": [
     "Diagnostic: a written leak list", "Sprint: fix it, build the systems", "Retainer: keep the seat filled"]}},

  # ---- E. Is it worth it ----
  {"vo": "The question that really matters. Is a fractional CFO worth it for a contractor your size?",
   "scene": "chapter", "c": {"num": "04", "title": "Is it worth it?"}},
  {"vo": "For most contractors at this size, yes, because the cost of not knowing your numbers is far larger than the fee. The average GC nets just five to six percent. Top performers pull ten to twelve.",
   "scene": "stat", "c": {"value": "5-6%", "label": "Average general contractor net margin in 2026", "source": "Industry construction-finance benchmarks (2026)"}},
  {"vo": "That gap is rarely a revenue problem. It is a cost-recognition and cash-timing problem, which is exactly what a CFO fixes.",
   "scene": "split_photo", "c": {"photo": P("three_roles"), "eyebrow": "The hidden gap", "title": "Average to best-in-class", "sub": "Usually a numbers problem, not a sales problem"}},
  {"vo": "Material costs made this urgent. Construction input prices rose nine point six percent in the year to May twenty twenty-six, with a single month jump of two point six percent, the fastest since the pandemic.",
   "scene": "stat", "c": {"value": "9.6%", "label": "Construction input price rise, year to May 2026", "source": "Associated Builders and Contractors / BLS (2026)"}},
  {"vo": "When inputs move that fast, an estimate built on last quarter's prices quietly turns a profitable job into a losing one. A CFO who watches job costs in real time catches that before it compounds across your backlog.",
   "scene": "split_photo", "c": {"photo": P("margin_squeeze"), "eyebrow": "Why timing matters", "title": "Stale prices, silent losses", "sub": "Copper and steel do not wait for your next estimate"}},
  {"vo": "Think of the fee as a percentage of the problem it solves. A five thousand a month retainer is sixty thousand a year. On a five million dollar contractor, recovering one point of margin is fifty thousand.",
   "scene": "stat", "c": {"value": "$50K", "label": "One point of margin recovered on a $5M contractor", "source": "Illustrative, on the industry margin base"}},
  {"vo": "Catch one under-billed change-order package, or tighten one slow draw cycle, and you clear the annual fee by itself. The question is not whether you can afford a CFO. It is whether you can afford to keep guessing.",
   "scene": "split_photo", "c": {"photo": P("draw_truck"), "eyebrow": "The math", "title": "The fee is small next to the leak", "sub": "One change order or one draw can pay for the year"}},
  {"vo": "There is a quieter return too. Contractors fail more from cash timing than from a lack of profit. A thirteen week cash forecast tells you the week cash gets tight, three months out.",
   "scene": "split_photo", "c": {"photo": P("cash_forecast"), "eyebrow": "Cheap insurance", "title": "See the tight week coming", "sub": "Arrange credit calmly, not in a crisis"}},

  # ---- F. When to hire ----
  {"vo": "So when should you actually hire one?",
   "scene": "chapter", "c": {"num": "05", "title": "When to hire"}},
  {"vo": "The clearest trigger is when the size of your decisions outgrows the quality of your numbers. That usually happens between one and five million in revenue.",
   "scene": "checklist", "c": {"title": "Signs it is time", "items": [
     "You cannot say which jobs made money last quarter",
     "A bonding company wants clean, reviewed statements",
     "You are preparing to sell or add a partner",
     "Profitable on paper, but the bank account disagrees"]}},
  {"vo": "You do not need to wait until you can afford a full-time hire. That is the whole point of the fractional model. Start with a diagnostic, see the leak list, and scale up only if the value is obvious.",
   "scene": "split_photo", "c": {"photo": P("decision_table"), "eyebrow": "No need to wait", "title": "Start small, scale on proof", "sub": "Buy the diagnostic first, decide with real numbers"}},

  # ---- G. CFO vs controller vs bookkeeper ----
  {"vo": "One more comparison people always ask about. What is the difference between a CFO, a controller, and a bookkeeper?",
   "scene": "chapter", "c": {"num": "06", "title": "Who does what"}},
  {"vo": "Three altitudes. A bookkeeper records transactions. A controller keeps them accurate and the close clean. A CFO uses the clean records to look forward. You need all three functions.",
   "scene": "compare", "c": {"title": "Three roles, three altitudes", "cols": ["CFO", "Controller", "Bookkeeper"],
     "rows": [("Records transactions", [False, False, True]), ("Job costing and WIP", [True, True, False]),
              ("Forward cash forecast", [True, False, False]), ("Bank and surety strategy", [True, False, False])]}},
  {"vo": "Only the CFO seat is hard to justify full time at this size. That is exactly why you buy it fractionally, while bookkeeping and controller work get handled in-house or bundled.",
   "scene": "split_photo", "c": {"photo": P("three_roles"), "eyebrow": "The takeaway", "title": "Buy the seat you cannot afford to fill", "sub": "At Salisbury CFO the bookkeeping is inside the fee"}},

  # ---- H. The offer + guarantee ----
  {"vo": "So how does Salisbury CFO price this, and what backs it?",
   "scene": "chapter", "c": {"num": "07", "title": "The offer and the guarantee"}},
  {"vo": "Three rungs. A fourteen-day Financial X-Ray at thirty-five hundred, ending in a written leak list. A six-week Profit Command Sprint at ninety-eight hundred to fourteen five. A Command Retainer at thirty-five hundred to twelve thousand a month, up to nine to twelve thousand for a fifteen-million-plus contractor.",
   "scene": "process", "c": {"title": "The Salisbury CFO ladder", "steps": [
     "14-Day Financial X-Ray: $3,500", "6-Week Profit Command Sprint: $9,800 to $14,500", "Command Retainer: $3,500 to $12,000 a month"]}},
  {"vo": "And it is backed by a three-x or you don't pay guarantee. The engagement returns at least three times its cost, in recovered margin, recovered cash, or avoided loss, or you do not pay.",
   "scene": "secure", "c": {"title": "Backed by a 3x guarantee", "items": [
     ("\U0001F4B0", "Recovered margin", "Profit that was leaking out of jobs"),
     ("\U0001F4B5", "Recovered cash", "Stuck retainage and slow draws, freed"),
     ("\U0001F6E1️", "Avoided loss", "Catching the losing job before it lands")]}},
  {"vo": "That only works for one reason. At a contractor doing one to twenty-five million, the financial leaks are almost always larger than the fee. We have seen a single engagement surface eighty-four hundred dollars in unbilled change orders inside sixty days.",
   "scene": "stat", "c": {"value": "$8,400", "label": "Unbilled change orders surfaced in 60 days, one client", "source": "Single client result, not an average"}},
  {"vo": "Recover thirty-four thousand in stuck retainage in a quarter. Cut a four and a half million dollar contractor's collection time to twenty-one days. Those are individual results. Yours will be your own. But the pattern is reliable.",
   "scene": "before_after", "c": {"before": P("before_stress"), "after": P("after_clean"),
     "caption": "Guessing at your numbers, to numbers you can defend"}},

  # ---- I. Close ----
  {"vo": "If you want the honest number for your company, start with the fourteen-day Financial X-Ray. In two weeks you get a written leak list, and you decide from there. No retainer required to find out.",
   "scene": "cta", "c": {"eyebrow": "Salisbury CFO", "title": "See your real number first", "sub": "Start with the 14-Day Financial X-Ray", "url": "salisburybookkeeping.com/contact"}},
]

if __name__ == "__main__":
    secs = ae.render_body(B, str(OUT), CACHE, voice="blend")
    print(f"BODY {secs:.1f}s ({secs/60:.1f} min), {len(B)} beats -> {OUT}")
