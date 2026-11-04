"""Pricebook video BODY — mirrors /blog/automate-servicetitan-pricebook-vendor-costs.html (GEO 1:1)."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)

IMG = str(HERE / "build/img/pricebook") + "/"
CACHE = HERE / "build/pricebook"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = HERE / "build/pricebook_body.mp4"
def P(n): return IMG + n + ".jpg"

B = [
  # ---- CH1: the problem ----
  {"vo": "If you run a residential service shop on ServiceTitan, your pricebook is the single most valuable spreadsheet in the company.",
   "scene": "photo", "c": {"photo": P("hero"), "eyebrow": "Top Builder AI · Pricebook", "title": "The book that runs the business", "sub": "Every quote starts here"}},
  {"vo": "It's where every quote, every option a tech presents at the kitchen table, and every dollar of margin is actually decided. And it's almost always out of date.",
   "scene": "split_photo", "c": {"photo": P("pricebook"), "eyebrow": "The quiet problem", "title": "It drifts out of date", "sub": "Vendors move; the book doesn't"}},
  {"vo": "Vendors raise prices all year. Copper, refrigerant, sheet metal, fittings, equipment — they all ride commodity cycles, and they move far more often than your pricebook does.",
   "scene": "photo", "c": {"photo": P("materials"), "eyebrow": "Costs that move", "title": "Copper. Refrigerant. Steel.", "sub": "Up through the year — every year"}},
  {"vo": "A price-increase letter shows up, gets glanced at, and never makes it into the book. So the costs in your pricebook drift away from the costs on your real invoices.",
   "scene": "split_photo", "c": {"photo": P("vendor"), "eyebrow": "How it goes stale", "title": "The letter never lands in the book", "sub": "Manual entry is the bottleneck"}},
  {"vo": "Here's why that quietly costs you. Flat-rate pricing has one structural weakness: you sell a price, not a receipt. The customer never sees your cost, so a cost error never corrects itself.",
   "scene": "split_photo", "c": {"photo": P("tech_quote"), "eyebrow": "Flat-rate's blind spot", "title": "You sell a price, not a receipt", "sub": "A cost error never self-corrects"}},
  {"vo": "If the price on the sheet is built on last spring's copper, every job that touches copper is quoted at last spring's margin — forever, until someone updates it.",
   "scene": "split_photo", "c": {"photo": P("margin_leak"), "eyebrow": "The leak", "title": "Last spring's margin, on today's jobs", "sub": "Until someone updates the sheet"}},
  {"vo": "And the sold-hour model amplifies it. Because the price is a formula, not a guess, a wrong input produces a precisely wrong output on every single ticket.",
   "scene": "stat", "c": {"value": "Every ticket", "label": "A wrong cost becomes a precisely wrong price on every job that item touches", "source": "the sold-hour formula"}},

  # ---- CH2: the math ----
  {"vo": "So let's put real numbers on it.", "scene": "chapter", "c": {"num": "01", "title": "The sold-hour model, in plain numbers"}},
  {"vo": "Most shops price like this: sold hours times your sold-hour rate, plus materials cost, plus your markup on those materials.",
   "scene": "define", "c": {"eyebrow": "The formula", "term": "Sold-hour pricing", "body": "price  =  sold hours × rate  +  materials cost  +  (materials cost × markup)"}},
  {"vo": "Take an air-conditioner install. Eight sold hours at a hundred fifty, plus about twenty-two hundred in materials at twenty percent markup. The book price comes out to thirty-eight sixty-four.",
   "scene": "stat", "c": {"value": "$3,864", "label": "AC install — 8 sold hours @ $150 + $2,220 materials @ 20% markup", "source": "illustrative"}},
  {"vo": "Now copper and refrigerant go up. Materials become twenty-two ninety-eight, and that same job should be thirty-nine fifty-seven. Quote the old price, and you just handed back the difference.",
   "scene": "stat", "c": {"value": "+$93.60", "label": "Same job re-prices to $3,957.60 (+2.4%) — on every install you sell", "source": "illustrative"}},

  # ---- CH3: how the agent keeps it current ----
  {"vo": "Here's the fix — and it isn't a once-a-year scramble.", "scene": "chapter", "c": {"num": "02", "title": "How an AI agent keeps it current"}},
  {"vo": "You connect your distributor's price file, and on a schedule the agent matches each new vendor cost to the SKUs on your pricebook items.",
   "scene": "split_photo", "c": {"photo": P("agent_review"), "eyebrow": "The Pricebook agent", "title": "Match vendor costs to your items", "sub": "On a schedule, automatically"}},
  {"vo": "It recomputes every affected item under your sold-hour model, and shows you the old price, the new price, and the exact margin change for each one.",
   "scene": "process", "c": {"title": "Every cycle, automatically", "steps": ["Ingest the vendor price update", "Recompute each item's material cost and price", "Show old price, new price, and margin change", "You approve the batch — it writes back to ServiceTitan"]}},
  {"vo": "You review the batch, approve it, and the approved prices write back into ServiceTitan. The AI never changes a customer-facing price on its own — a person approves it first.",
   "scene": "photo_overlay", "c": {"photo": P("agent_review"), "overlay": "booked", "title": "Approved — written back to ServiceTitan", "sub": "Human-approved, every time"}},
  {"vo": "Run it quarterly, and you're reviewing a clean, current diff four times a year — instead of letting the whole book quietly rot.",
   "scene": "stat", "c": {"value": "Quarterly", "label": "A clean, approved diff four times a year — not a once-a-year panic", "source": "recommended cadence"}},

  # ---- CH4: import vs continuous ----
  {"vo": "And this is the real difference from the tools shops already use.", "scene": "chapter", "c": {"num": "03", "title": "One-time import vs. continuous sync"}},
  {"vo": "A one-time import gets you current once, then drifts again. The agent's whole job is the part that keeps happening: continuous, approved, vendor-cost-driven re-pricing.",
   "scene": "compare", "c": {"title": "Keeping the book current", "cols": ["One-time import", "Pricebook Pro", "Top Builder AI"],
     "rows": [("Ongoing vendor-cost updates", [False, False, True]),
              ("Re-prices under your sold-hour model", [False, True, True]),
              ("Shows margin impact per item", [False, False, True]),
              ("Human approves every change", [True, True, True]),
              ("Continuous, scheduled sync", [False, False, True])]}},

  # ---- CH5: safe ----
  {"vo": "Because it's touching your prices, it's built to be safe.", "scene": "chapter", "c": {"num": "04", "title": "Safe by design"}},
  {"vo": "Nothing posts without your approval. Every change is reversible. And the numbers come from deterministic, tested code — the AI explains them, it never makes them up.",
   "scene": "secure", "c": {"title": "How it stays safe", "items": [("✅", "Human-approved", "No price change without you approving the batch"),
     ("↩", "Reversible", "Every write-back can be undone"), ("🔒", "Deterministic", "Tested code computes the figure — the AI only explains it")]}},

  # ---- CH6: before/after + CTA ----
  {"vo": "So the shift is simple.", "scene": "chapter", "c": {"num": "05", "title": "What actually changes"}},
  {"vo": "You go from a pricebook nobody fully trusts and a margin leak nobody can trace, to a book that's current every quarter and margins that hold.",
   "scene": "before_after", "c": {"before": P("before_stress"), "after": P("after_calm"), "caption": "A book you can't trust → one that's always current"}},
  {"vo": "Your techs quote with confidence, because the number on the tablet reflects what the job actually costs today — not last spring.",
   "scene": "split_photo", "c": {"photo": P("handshake"), "eyebrow": "The outcome", "title": "Quote with confidence", "sub": "Today's costs, on every ticket"}},
  {"vo": "If your pricebook is older than your last few vendor increases, it's leaking margin right now. Read the full guide on the blog, then book a call and we'll run it against your real book.",
   "scene": "cta", "c": {"eyebrow": "Top Builder AI · for ServiceTitan contractors", "title": "See it run against your pricebook", "sub": "Read the guide, then book a 30-minute fit call", "url": "topbuilderai.com/blog"}},
]

if __name__ == "__main__":
    secs = ae.render_body(B, str(OUT), CACHE)
    print(f"BODY {secs:.1f}s ({secs/60:.1f} min), {len(B)} beats -> {OUT}")
