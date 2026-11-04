"""Top Practice CFO long-form video BODY: "Fractional CFO for med spas: the complete guide."
Mirrors the med spa cornerstone post's citation rhythm: open shallow, answer first, escalate one buyer
question per chapter with a defensible range/example + a takeaway. Narration = cory-voice BLEND.
Legal-structure and comp-legality topics are framed as coordinate-with-your-attorney (no legal advice).
Honest ranges only; numbers normalized for the ear. HeyGen intro + this BODY + reused generic outro."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)
IMG = str(HERE / "build/img/medspaguide") + "/"
CACHE = HERE / "build/medspaguide"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = HERE / "build/medspaguide_body.mp4"
def P(n): return IMG + n + ".jpg"

B = [
  # ---- A. Shallow question + answer-first ----
  {"vo": "What does a fractional CFO actually do for a med spa, and is it worth it? Let us answer it straight, with real numbers.",
   "scene": "title", "c": {"eyebrow": "Fractional CFO for med spas", "title": "The complete guide", "sub": "What it does, what it costs, and when to hire one"}},
  {"vo": "Here is the short answer. A fractional CFO gives an owner-operated med spa senior financial leadership for a few days a month, usually three thousand five hundred to seven thousand five hundred dollars on a flat monthly retainer.",
   "scene": "stat", "c": {"value": "$3.5K-$7.5K", "label": "Per month for an owner-operated med spa", "source": "Typical fractional CFO retainer, $1M to $10M practices"}},
  {"vo": "That is a fraction of a full-time hire, and for most med spas doing one to ten million it is the right level of help. Let me walk you through what you get, and how to tell if it fits your practice.",
   "scene": "split_photo", "c": {"photo": P("hero"), "eyebrow": "Top Practice CFO", "title": "Built for owner-operated med spas", "sub": "Senior finance, sized to a clinician-owned practice"}},

  # ---- CH01 what it does ----
  {"vo": "First question. What does a fractional CFO actually do that your bookkeeper and CPA do not?",
   "scene": "chapter", "c": {"num": "01", "title": "What a fractional CFO does"}},
  {"vo": "A bookkeeper records what happened. A CPA keeps you compliant and files taxes. A fractional CFO sits above both and turns those clean records into decisions: profit by service line, provider pay, a cash forecast, membership economics, and exit prep.",
   "scene": "cards", "c": {"title": "The core work", "items": [
     ("\U0001F4CA", "Profit by service line"), ("\U0001F4C5", "A 13-week cash forecast"),
     ("\U0001F489", "Provider pay modeling"), ("\U0001F4C8", "Membership and exit math")]}},
  {"vo": "For a med spa the work centers on the things that quietly move profit. Injectable margin after product and provider time, membership economics, and the mix across injectables, laser, memberships, and retail.",
   "scene": "split_photo", "c": {"photo": P("treatment_room"), "eyebrow": "Tuned to med spa economics", "title": "Where a med spa really makes money", "sub": "Injectables, laser, memberships, and retail each behave differently"}},
  {"vo": "Think of it this way. The bookkeeper says what happened, the CPA says what is owed, and the CFO says what to do next. That last seat is the one most med spas are missing.",
   "scene": "define", "c": {"eyebrow": "The simple version", "term": "The decision seat", "body": "Records and tax filings look backward. A fractional CFO is the forward-looking seat that turns them into the next decision."}},

  # ---- CH02 when to hire ----
  {"vo": "Next. Do med spas actually need a CFO, and when?",
   "scene": "chapter", "c": {"num": "02", "title": "Do you need one, and when"}},
  {"vo": "The clearest trigger is when the size of your decisions outgrows the quality of your numbers. That usually happens somewhere between one and ten million in revenue.",
   "scene": "checklist", "c": {"title": "Signs it is time", "items": [
     "You cannot say which services made money last quarter",
     "You are adding a second injector, a device, or a location",
     "Memberships are growing but cash still feels tight",
     "Profitable on paper, but the bank account disagrees"]}},
  {"vo": "Below about a million in revenue, solid bookkeeping and a good CPA are usually the better first spend. Above it, the decisions get expensive to guess at, and that is where a fractional CFO earns the fee.",
   "scene": "split_photo", "c": {"photo": P("owner_worry"), "eyebrow": "Right-sized", "title": "Start when the decisions get big", "sub": "You do not need to wait for a full-time hire"}},

  # ---- CH03 med-spa-specific problems ----
  {"vo": "Now the real question. What med spa problems does a CFO solve that a generic accountant cannot?",
   "scene": "chapter", "c": {"num": "03", "title": "The med spa specifics"}},
  {"vo": "Start with injectables. Most owners price off product cost alone. The true loaded margin also has to subtract injector pay, room and overhead time, and product waste. A unit that looks profitable can be thin once you load it fully.",
   "scene": "split_photo", "c": {"photo": P("injectables"), "eyebrow": "Loaded, not list", "title": "The real margin on an injectable", "sub": "Product, plus injector time, room, and waste"}},
  {"vo": "Laser and devices are a different shape. You are paying for a lease and for capacity, so the question is utilization, not unit cost. Idle device time is pure margin leak.",
   "scene": "split_photo", "c": {"photo": P("laser_device"), "eyebrow": "Capacity, not units", "title": "Devices live or die on utilization", "sub": "A lease you do not keep busy is a loss"}},
  {"vo": "And payroll is the cliff. In a healthy med spa, total payroll generally sits below about forty percent of revenue. When provider compensation creeps past that, profit disappears fast, and most owners cannot see it happening.",
   "scene": "stat", "c": {"value": "Under 40%", "label": "Healthy total payroll as a share of revenue", "source": "Commonly cited med spa benchmark; above it, profit erodes"}},

  # ---- CH04 structure ----
  {"vo": "A question unique to medical aesthetics. How should the business be structured?",
   "scene": "chapter", "c": {"num": "04", "title": "Structure and provider pay"}},
  {"vo": "Many med spas run a management company alongside a professional entity, with a management fee between them. That structure is set up with your attorney. The CFO models the management-fee flow and keeps the economics clean.",
   "scene": "split_photo", "c": {"photo": P("provider_comp"), "eyebrow": "Coordinate with counsel", "title": "The MSO and PC question", "sub": "Your attorney sets the structure; the CFO models the numbers"}},
  {"vo": "Provider pay is the same story. Paying a percent of revenue is common, but the rules in some states limit commission on the medical-service portion. Treat that as a structure question for your attorney, and let the CFO build pay that is both motivating and profitable.",
   "scene": "define", "c": {"eyebrow": "Not legal advice", "term": "Compensation, done carefully", "body": "Coordinate provider-comp legality with your attorney. The CFO designs the economics so the pay plan still clears a margin."}},

  # ---- CH05 memberships ----
  {"vo": "Now the one owners love and fear. Are memberships a cash machine or a margin trap?",
   "scene": "chapter", "c": {"num": "05", "title": "Membership economics"}},
  {"vo": "Memberships smooth cash, which feels great. But prepaid dues create deferred revenue, money you have collected for services you still owe. The cash in the bank is partly a future obligation, not profit.",
   "scene": "split_photo", "c": {"photo": P("service_lines"), "eyebrow": "The cash illusion", "title": "Deferred revenue is not profit", "sub": "You hold the cash, but you still owe the service"}},
  {"vo": "Whether a membership actually pays comes down to contribution margin and breakage. Price it wrong and the included services cost more than the dues, and a growing membership quietly grows a loss.",
   "scene": "compare", "c": {"title": "When a membership pays", "cols": ["Healthy", "Trap"],
     "rows": [("Dues exceed loaded service cost", [True, False]), ("Tracked as deferred revenue", [True, False]),
              ("Drives retail and rebooking", [True, False]), ("Priced off a discount guess", [False, True])]}},

  # ---- CH06 owner take-home + cash ----
  {"vo": "Here is the question behind the cash squeeze. Why is a profitable med spa still tight in the bank, and what fixes it?",
   "scene": "chapter", "c": {"num": "06", "title": "Cash and owner pay"}},
  {"vo": "Profit and cash are not the same thing. Between deferred revenue, product orders, device leases, and slow weeks, a profitable month can still leave the account thin. A thirteen week cash forecast shows the tight week three months out.",
   "scene": "split_photo", "c": {"photo": P("cash_forecast"), "eyebrow": "See it coming", "title": "13 weeks of cash on one view", "sub": "Arrange credit calmly, not in a crisis"}},
  {"vo": "And owner pay deserves a structure. The common path is a reasonable salary plus distributions, coordinated with your CPA, so the owner is paid predictably instead of taking whatever is left.",
   "scene": "process", "c": {"title": "Steady owner take-home", "steps": [
     "A reasonable salary, set with your CPA", "Distributions from real profit", "A cash reserve so pay is predictable"]}},

  # ---- CH07 cost + ROI ----
  {"vo": "So how much does this cost, and is it worth it?",
   "scene": "chapter", "c": {"num": "07", "title": "Cost and ROI"}},
  {"vo": "A full-time finance executive runs roughly one hundred eighty thousand to two hundred fifty thousand dollars a year all in. A fractional CFO is about twenty to thirty percent of that, for the slice of senior judgment you actually need.",
   "scene": "compare", "c": {"title": "Full-time versus fractional", "cols": ["Fractional", "Full-time CFO"],
     "rows": [("CFO-level judgment", [True, True]), ("Six-figure salary", [False, True]),
              ("Months-long search", [False, True]), ("Sized to your real need", [True, False])]}},
  {"vo": "Judge the fee against what it recovers, not the invoice. One correctly priced injectable line, one membership fixed, or one payroll reset can return the retainer many times over.",
   "scene": "split_photo", "c": {"photo": P("valuation_review"), "eyebrow": "The math", "title": "The fee is small next to the leak", "sub": "One repriced service line can pay for the year"}},
  {"vo": "There is a longer return too. Med spas are valued on a multiple of normalized earnings. Durable membership revenue can lift the multiple, while leaning on a single injector can discount it. A CFO builds that value in the years before you sell.",
   "scene": "split_photo", "c": {"photo": P("exit_handshake"), "eyebrow": "Built years early", "title": "Worth more when you sell", "sub": "Recurring revenue up, single-provider risk down"}},

  # ---- CH08 how to choose + method ----
  {"vo": "Last questions. How do you choose the right fractional CFO, and how do you keep the numbers honest?",
   "scene": "chapter", "c": {"num": "08", "title": "Choosing, and trust"}},
  {"vo": "Choose one who knows med spa economics, who works alongside your existing bookkeeper and CPA, and who states pricing and scope in plain terms. The method matters too.",
   "scene": "split_photo", "c": {"photo": P("retail_shelf"), "eyebrow": "What to look for", "title": "Specialist, transparent, collaborative", "sub": "Med spa fluency, plain pricing, plays well with your CPA"}},
  {"vo": "The method is built so the artificial intelligence never computes a number on its own. Data is pulled from the source, every figure is computed in code, the AI only narrates and flags, and a human CFO reviews the result before it reaches you.",
   "scene": "secure", "c": {"title": "The AI never computes a number", "items": [
     ("\U0001F50C", "Pulled from the source", "Straight from your ledger, not guessed"),
     ("\U0001F9EE", "Computed in code", "Math in code, never in a language model"),
     ("\U0001F9D1", "Reviewed by a CFO", "A human signs off before you see it")]}},

  # ---- offer + before/after ----
  {"vo": "So how does Top Practice CFO price this? Most owners start with a fourteen-day Financial X-ray, a written look at recoverable cash, margin, and tax, before any ongoing retainer.",
   "scene": "process", "c": {"title": "How to start", "steps": [
     "14-Day Financial X-ray: a written profit and cash read", "Ongoing retainer: $3,500 to $7,500 a month", "Backed by a 3x-or-you-do-not-pay guarantee"]}},
  {"vo": "And it is backed by a simple guarantee. In your first ninety days we identify at least three times the fee in recoverable cash, margin, or tax, quantified in writing, or you do not pay for those ninety days.",
   "scene": "secure", "c": {"title": "Backed by a 3x guarantee", "items": [
     ("\U0001F4B0", "Recovered margin", "Profit leaking out of service lines"),
     ("\U0001F4B5", "Recovered cash", "Deferred revenue and slow weeks, managed"),
     ("\U0001F6E1️", "Avoided tax", "Moves left on the table, claimed")]}},
  {"vo": "The reason that works is simple. In an owner-operated med spa the financial leaks are almost always larger than the fee. You just cannot see them until someone computes them from your real numbers.",
   "scene": "before_after", "c": {"before": P("before_stress"), "after": P("after_calm"),
     "caption": "Guessing at your numbers, to numbers you can defend"}},

  # ---- close ----
  {"vo": "If you want the honest picture for your med spa, start with the fourteen-day Financial X-ray. In two weeks you get a written view of your profit and cash, and you decide from there.",
   "scene": "cta", "c": {"eyebrow": "Top Practice CFO", "title": "See your real numbers first", "sub": "Start with the 14-Day Financial X-ray", "url": "toppracticecfo.com/how-we-work"}},
]

if __name__ == "__main__":
    secs = ae.render_body(B, str(OUT), CACHE, voice="blend")
    print(f"BODY {secs:.1f}s ({secs/60:.1f} min), {len(B)} beats -> {OUT}")
