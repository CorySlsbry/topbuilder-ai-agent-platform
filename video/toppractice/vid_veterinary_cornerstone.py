"""Top Practice CFO long-form video BODY: "Fractional CFO for veterinary practices: the complete guide."
Mirrors the cornerstone post's citation rhythm: open shallow, answer first, escalate one buyer question
per chapter with a defensible range/example + a takeaway. ~42 beats. Narration = cory-voice BLEND.
HeyGen avatar INTRO (build/intro.mp4) + this BODY + HeyGen avatar OUTRO (build/outro.mp4), assembled by
make_vet_video.py. Honest ranges only (no fabricated precise stats); numbers normalized for the ear."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)
IMG = str(HERE / "build/img/vetguide") + "/"
CACHE = HERE / "build/vetguide"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = HERE / "build/vetguide_body.mp4"
def P(n): return IMG + n + ".jpg"

B = [
  # ---- A. Shallow question + answer-first ----
  {"vo": "What does a fractional CFO actually do for a veterinary practice, and is it worth it? Let us answer it straight, with real numbers.",
   "scene": "title", "c": {"eyebrow": "Fractional CFO for veterinary practices", "title": "The complete guide", "sub": "What it does, what it costs, and when to hire one"}},
  {"vo": "Here is the short answer. A fractional CFO gives an owner-operated practice senior financial leadership for a few days a month, usually three thousand five hundred to seven thousand five hundred dollars on a flat monthly retainer.",
   "scene": "stat", "c": {"value": "$3.5K-$7.5K", "label": "Per month for an owner-operated veterinary practice", "source": "Typical fractional CFO retainer, $1M to $10M practices"}},
  {"vo": "That is a fraction of a full-time hire, and for most practices doing one to ten million it is the right level of help. Let me walk you through exactly what you get, and how to tell if it fits your practice.",
   "scene": "split_photo", "c": {"photo": P("hero"), "eyebrow": "Top Practice CFO", "title": "Built for owner-operated practices", "sub": "Veterinary is the flagship, with med spa as the second niche"}},

  # ---- CH01 what it does ----
  {"vo": "First question. What does a fractional CFO actually do that your bookkeeper and CPA do not?",
   "scene": "chapter", "c": {"num": "01", "title": "What a fractional CFO does"}},
  {"vo": "A bookkeeper records what already happened. A CPA keeps you compliant and files the taxes. A fractional CFO sits above both and turns those clean records into decisions: forecasting, profit by service line, doctor pay, cash, and exit planning.",
   "scene": "cards", "c": {"title": "The core work", "items": [
     ("\U0001F4CA", "Profit by service line"), ("\U0001F4C5", "A 13-week cash forecast"),
     ("\U0001FA7A", "Doctor pay modeling"), ("\U0001F4C8", "Exit and valuation prep")]}},
  {"vo": "For a veterinary hospital the work centers on the issues that actually move profit. Production-based doctor pay, pharmacy margin, and the mix across wellness, surgery, and dental.",
   "scene": "split_photo", "c": {"photo": P("exam_room"), "eyebrow": "Tuned to vet economics", "title": "Where a practice really makes money", "sub": "Wellness, surgery, dental, and pharmacy each behave differently"}},
  {"vo": "Think of it this way. The bookkeeper says what happened, the CPA says what is owed, and the CFO says what to do next. That last seat is the one most practices are missing.",
   "scene": "define", "c": {"eyebrow": "The simple version", "term": "The decision seat", "body": "Records and tax filings look backward. A fractional CFO is the forward-looking seat that turns them into the next decision."}},

  # ---- CH02 cost vs full-time ----
  {"vo": "Next question. Why is fractional so much cheaper than hiring a CFO full time?",
   "scene": "chapter", "c": {"num": "02", "title": "What it costs, and why"}},
  {"vo": "Because a full-time finance executive is expensive. All in, with salary, bonus, and benefits, a full-time CFO runs roughly one hundred eighty thousand to two hundred fifty thousand dollars a year.",
   "scene": "stat", "c": {"value": "$180K-$250K", "label": "Full-time CFO, all-in, per year", "source": "Salary, bonus, and benefits combined"}},
  {"vo": "A fractional CFO shares one experienced person across a handful of practices. You get the same caliber of judgment on the slice of time you actually need, for about twenty to thirty percent of that cost.",
   "scene": "compare", "c": {"title": "Full-time versus fractional", "cols": ["Fractional", "Full-time CFO"],
     "rows": [("CFO-level judgment", [True, True]), ("Six-figure salary", [False, True]),
              ("Months-long search", [False, True]), ("Sized to your real need", [True, False])]}},
  {"vo": "Most practices doing one to ten million do not have a quarter million dollars of CFO work every year. They have a few high-stakes decisions and a constant worry about cash.",
   "scene": "split_photo", "c": {"photo": P("money_vs_seat"), "eyebrow": "The real need", "title": "A few big calls, and the cash worry", "sub": "Fractional is sized to exactly that"}},

  # ---- CH03 profit by service line ----
  {"vo": "Now the question most owners cannot answer. Which of your services actually make money?",
   "scene": "chapter", "c": {"num": "03", "title": "Profit by service line"}},
  {"vo": "Most owners can quote revenue to the dollar but not profit by line, after doctor compensation and overhead. When you finally see it, pricing and scheduling decisions get obvious.",
   "scene": "split_photo", "c": {"photo": P("service_lines"), "eyebrow": "Revenue is not profit", "title": "True profit per service", "sub": "Wellness, surgery, dental, and pharmacy, after comp and overhead"}},
  {"vo": "Pharmacy is the classic example. In-house pharmacy margin quietly erodes to online pharmacies, so a line that looks like a profit center can be barely breaking even once you load it fully.",
   "scene": "split_photo", "c": {"photo": P("pharmacy"), "eyebrow": "The quiet leak", "title": "Where pharmacy margin goes", "sub": "Loaded cost, not shelf price, tells the truth"}},
  {"vo": "Healthy benchmarks help you spot the leaks. Cost of goods commonly runs about twenty to twenty-seven percent, total payroll about twenty to thirty percent, and operating profit roughly fifteen to twenty-five percent. Below about twelve percent profit is a warning sign.",
   "scene": "stat", "c": {"value": "15-25%", "label": "Healthy operating profit margin range", "source": "Commonly cited veterinary practice benchmarks"}},

  # ---- CH04 DVM comp ----
  {"vo": "Here is a question that catches busy practices off guard. Is production-based doctor pay quietly eating your margin?",
   "scene": "chapter", "c": {"num": "04", "title": "Doctor compensation"}},
  {"vo": "When doctor compensation is tied to production, a busy month can still be an unprofitable one if the comp curve outpaces the margin. There is a crossover point, and most owners cannot see where theirs sits.",
   "scene": "split_photo", "c": {"photo": P("dvm_comp"), "eyebrow": "The margin crossover", "title": "Busy is not the same as profitable", "sub": "Production pay can outrun the margin it generates"}},
  {"vo": "Owner pay deserves the same structure. The cleanest way is three parts. Clinical production pay, commonly eighteen to twenty-two percent of your own production. A management portion, commonly three to four percent of practice revenue. And a return on owning the business, paid out of true profit.",
   "scene": "process", "c": {"title": "Owner pay, in three parts", "steps": [
     "Clinical production pay for the medicine you do", "A management portion for running the business", "A return on equity for owning it"]}},

  # ---- CH05 cash ----
  {"vo": "Next. Why is a profitable practice still tight on cash, and what fixes it?",
   "scene": "chapter", "c": {"num": "05", "title": "Cash flow"}},
  {"vo": "Most practices run on the bank balance and a gut feel. A thirteen week rolling cash forecast removes the surprises, payroll, pharmacy restock, equipment, and the slow seasons, and shows you the tight week three months out.",
   "scene": "split_photo", "c": {"photo": P("cash_forecast"), "eyebrow": "See it coming", "title": "13 weeks of cash on one view", "sub": "Arrange credit calmly, not in a crisis"}},
  {"vo": "Profit and cash are not the same thing. You can have a strong year on paper and still scramble at payroll, because cash is timing and profit is accrual. The forecast is how you stop being surprised.",
   "scene": "define", "c": {"eyebrow": "The distinction", "term": "Profit is not cash", "body": "Profit is what you earned; cash is when it actually arrives. A 13-week forecast manages the gap."}},

  # ---- CH06 exit / valuation ----
  {"vo": "Now a high-stakes one. What is your practice worth, and how do you get exit-ready?",
   "scene": "chapter", "c": {"num": "06", "title": "Valuation and exit"}},
  {"vo": "Veterinary groups are rolling up practices fast, and the offers arrive whether or not you are ready. Practices are valued on a multiple of normalized earnings, so the work is to clean and normalize that earnings number.",
   "scene": "split_photo", "c": {"photo": P("valuation_review"), "eyebrow": "Know your number", "title": "Valued on normalized EBITDA", "sub": "The add-backs most owners miss are the gap between offer and value"}},
  {"vo": "As a rough guide, independent practices commonly trade around three to five times adjusted earnings, while corporate and consolidator buyers can pay higher multiples, often in the six to twelve times range, for larger practices.",
   "scene": "stat", "c": {"value": "6-12x", "label": "Corporate / consolidator EBITDA multiple range", "source": "Commonly cited ranges; independents nearer 3 to 5x"}},
  {"vo": "Owners who know their real profit, their cash, and their multiple negotiate from strength. Even if you never sell, that knowledge is leverage, and it is the work a CFO does in the twelve to thirty-six months before any sale.",
   "scene": "split_photo", "c": {"photo": P("exit_handshake"), "eyebrow": "Negotiate from strength", "title": "Ready, whether or not you sell", "sub": "The multiple is built years before the offer"}},

  # ---- CH07 when to hire ----
  {"vo": "So when should a practice actually hire a fractional CFO?",
   "scene": "chapter", "c": {"num": "07", "title": "When to hire"}},
  {"vo": "The clearest trigger is when the size of your decisions outgrows the quality of your numbers. That usually happens somewhere between one and ten million in revenue.",
   "scene": "checklist", "c": {"title": "Signs it is time", "items": [
     "You cannot say which services made money last quarter",
     "Production-based pay is climbing faster than profit",
     "Acquisition offers are arriving and you are not sure you are ready",
     "Profitable on paper, but the bank account disagrees"]}},
  {"vo": "You do not need to wait until you can afford a full-time hire. That is the whole point of the fractional model. Start small, see the value, and scale only if it is obvious.",
   "scene": "split_photo", "c": {"photo": P("owner_worry"), "eyebrow": "No need to wait", "title": "Start small, scale on proof", "sub": "The fractional model is built for exactly this stage"}},

  # ---- CH08 CFO vs CPA vs bookkeeper ----
  {"vo": "One comparison owners always ask about. What is the difference between a CFO, a CPA, and a bookkeeper?",
   "scene": "chapter", "c": {"num": "08", "title": "Who does what"}},
  {"vo": "Three altitudes. A bookkeeper records transactions. A CPA files taxes and keeps you compliant. A fractional CFO uses those clean records to look forward, on pricing, margin, cash, pay, and exit value. You need all three functions.",
   "scene": "compare", "c": {"title": "Three roles, three altitudes", "cols": ["CFO", "CPA", "Bookkeeper"],
     "rows": [("Records transactions", [False, False, True]), ("Files taxes", [False, True, False]),
              ("Profit by service line", [True, False, False]), ("Forward cash and exit", [True, False, False])]}},
  {"vo": "Only the CFO seat is hard to justify full time at this size. That is exactly why you buy it fractionally, while bookkeeping and tax stay where they are.",
   "scene": "split_photo", "c": {"photo": P("three_roles"), "eyebrow": "The takeaway", "title": "Buy the seat you cannot fill", "sub": "We work alongside your existing bookkeeper and CPA"}},

  # ---- CH09 how the numbers stay right ----
  {"vo": "Last question, and an important one. With all this automation, how do you keep the numbers honest?",
   "scene": "chapter", "c": {"num": "09", "title": "How the numbers stay right"}},
  {"vo": "The method is built so the artificial intelligence never computes a number on its own. Data is pulled from the source, every figure is computed in code, the AI only narrates and flags what the numbers show, and a human CFO reviews the result before it reaches you.",
   "scene": "secure", "c": {"title": "The AI never computes a number", "items": [
     ("\U0001F50C", "Pulled from the source", "Straight from your ledger, not guessed"),
     ("\U0001F9EE", "Computed in code", "Math in code, never in a language model"),
     ("\U0001F9D1", "Reviewed by a CFO", "A human signs off before you see it")]}},
  {"vo": "That separation keeps the speed of automation while protecting against confident, wrong math. Lead CFO Cory Salisbury reviews the analysis, so every figure has passed through both code and a person.",
   "scene": "split_photo", "c": {"photo": P("after_calm"), "eyebrow": "Speed with trust", "title": "Automated, then human-checked", "sub": "Every number is computed from your ledger and reviewed by a CFO"}},

  # ---- the offer + before/after ----
  {"vo": "So how does Top Practice CFO price this? Most owners start with a fourteen-day Financial X-ray, a written look at recoverable cash, margin, and tax, before any ongoing retainer.",
   "scene": "process", "c": {"title": "How to start", "steps": [
     "14-Day Financial X-ray: a written profit and cash read", "Ongoing retainer: $3,500 to $7,500 a month", "Backed by a 3x-or-you-do-not-pay guarantee"]}},
  {"vo": "And it is backed by a simple guarantee. In your first ninety days we identify at least three times the fee in recoverable cash, margin, or tax, quantified in writing, or you do not pay for those ninety days.",
   "scene": "secure", "c": {"title": "Backed by a 3x guarantee", "items": [
     ("\U0001F4B0", "Recovered margin", "Profit leaking out of service lines"),
     ("\U0001F4B5", "Recovered cash", "Slow collections and stuck inventory, freed"),
     ("\U0001F6E1️", "Avoided tax", "Moves left on the table, claimed")]}},
  {"vo": "The reason that works is simple. In an owner-operated practice the financial leaks are almost always larger than the fee. You just cannot see them until someone computes them from your real numbers.",
   "scene": "before_after", "c": {"before": P("before_stress"), "after": P("after_calm"),
     "caption": "Guessing at your numbers, to numbers you can defend"}},

  # ---- close ----
  {"vo": "If you want the honest picture for your practice, start with the fourteen-day Financial X-ray. In two weeks you get a written view of your profit and cash, and you decide from there.",
   "scene": "cta", "c": {"eyebrow": "Top Practice CFO", "title": "See your real numbers first", "sub": "Start with the 14-Day Financial X-ray", "url": "toppracticecfo.com/how-we-work"}},
]

if __name__ == "__main__":
    secs = ae.render_body(B, str(OUT), CACHE, voice="blend")
    print(f"BODY {secs:.1f}s ({secs/60:.1f} min), {len(B)} beats -> {OUT}")
