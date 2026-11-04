"""Pricebook Pro vs. self-learning agent — long-form BODY (mirrors
/blog/servicetitan-pricebook-pro-vs-self-learning-agent.html, the question ladder 1:1).
Hook lives in the HeyGen intro (hooks.py + viral_score.py); this is hook-answered -> body-teaches.
Reuses the existing pricebook image pool ($0 new spend, REUSE-FIRST, this lane's asset tier is free)."""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)

IMG = str(HERE / "build/img/pricebook") + "/"
CACHE = HERE / "build/pricebook_pro_lf"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = HERE / "build/pricebook_pro_lf_body.mp4"
def P(n): return IMG + n + ".jpg"

B = [
  # ---- land the promise the intro made ----
  {"vo": "So let's answer that for real, straight from ServiceTitan's own documentation, not a guess.",
   "scene": "photo", "c": {"photo": P("hero"), "eyebrow": "Top Builder AI · Pricebook", "title": "Pricebook Pro vs. a self-learning agent", "sub": "What each one actually updates"}},

  # ---- CH1: what Pricebook Pro updates ----
  {"vo": "Question one. What does Pricebook Pro actually update, and how often?", "scene": "chapter", "c": {"num": "01", "title": "What Pricebook Pro updates"}},
  {"vo": "ServiceTitan's own feature page says Pricebook Pro delivers regular content updates to costs, images, descriptions, and sold hours. That sounds continuous. It isn't.",
   "scene": "split_photo", "c": {"photo": P("pricebook"), "eyebrow": "The marketing page", "title": "\"Regular content updates\"", "sub": "The detail is in the help docs, not the pitch"}},
  {"vo": "ServiceTitan's own help article, comparing Pricebook Pro and Pricebook Connect directly, says Pricebook Pro's content is generic, and it's updated monthly, by ServiceTitan. Not your vendor. Not your SKU. Monthly, generic content.",
   "scene": "stat", "c": {"value": "Monthly", "label": "Pricebook Pro content updates are generic and set by ServiceTitan, not tied to your vendor's actual cost changes", "source": "help.servicetitan.com, Pricebook Pro and Pricebook Connect Differences"}},

  # ---- CH2: is Connect the same thing ----
  {"vo": "Question two. Isn't Pricebook Connect the same thing?", "scene": "chapter", "c": {"num": "02", "title": "Pricebook Connect is a separate product"}},
  {"vo": "No. ServiceTitan is explicit about this: Pricebook Pro and Pricebook Connect are separate products. Connect is the marketplace area where vendor and manufacturer catalogs actually live.",
   "scene": "split_photo", "c": {"photo": P("vendor"), "eyebrow": "Two different products", "title": "Pro ≠ Connect", "sub": "You can have one without the other"}},
  {"vo": "Where Pricebook Pro's updates are ServiceTitan's own content on a monthly clock, Connect's updates are vendor-specific, and they land at the supplier's discretion — whenever your distributor decides to publish a new price.",
   "scene": "define", "c": {"eyebrow": "The real split", "term": "Discretion", "body": "Pricebook Connect's vendor cost updates sync on the supplier's own schedule — not yours"}},

  # ---- CH3: what happens when a vendor raises a price in Connect ----
  {"vo": "Question three. What actually happens when a vendor raises a price in Connect?", "scene": "chapter", "c": {"num": "03", "title": "One material, applied by hand"}},
  {"vo": "By ServiceTitan's own walkthrough: once a material is mapped to a vendor catalog, a cost change syncs overnight and shows up in the Updates screen with an asterisk and the dollar delta. Their own example — twenty dollars twenty-five cents to twenty-four twenty-five.",
   "scene": "split_photo", "c": {"photo": P("materials"), "eyebrow": "Pricebook Connect", "title": "The Updates screen", "sub": "One material line, flagged with a dollar delta"}},
  {"vo": "Then a person applies it — manually, or through a bulk action — to that one material item. That's the whole documented workflow. One line, applied by hand.",
   "scene": "stat", "c": {"value": "+$4.25", "label": "ServiceTitan's own example: a coupling moves $20.25 → $24.25 — for you to apply, item by item", "source": "help.servicetitan.com, Update your pricebook with Pricebook Connect"}},

  # ---- CH4: the gap in one sentence ----
  {"vo": "Question four. So what's the actual gap, in one sentence?", "scene": "chapter", "c": {"num": "04", "title": "The gap"}},
  {"vo": "That one material is usually built into dozens of different flat-rate service and assembly items. Pricebook Connect tells you the material moved. It doesn't walk you through every service item built on top of it.",
   "scene": "split_photo", "c": {"photo": P("margin_leak"), "eyebrow": "The blind spot", "title": "One material, many items", "sub": "Nothing recomputes the rest of the book"}},
  {"vo": "Neither Pricebook Pro nor Pricebook Connect turns \"this material went up four twenty-five\" into \"here are the service items that touches, and here's the price and margin move on each.\" That recompute-and-total step is the gap.",
   "scene": "stat", "c": {"value": "The recompute step", "label": "Neither tool turns one material's cost delta into a reviewed, margin-aware price update across the whole book", "source": "ServiceTitan's own documented workflow"}},

  # ---- CH5: how the agent closes the gap ----
  {"vo": "Question five. How does a self-learning Pricebook agent close that gap?", "scene": "chapter", "c": {"num": "05", "title": "How the agent closes it"}},
  {"vo": "It ingests the same vendor cost update — from Connect if you run it, or straight from a distributor's price file — and works the same math a fractional CFO would check by hand.",
   "scene": "split_photo", "c": {"photo": P("agent_review"), "eyebrow": "The Pricebook agent", "title": "Same feed, the missing math", "sub": "Sold hours × rate + materials cost + markup"}},
  {"vo": "Here's the full pass, step by step.", "scene": "process", "c": {"title": "One vendor cost update, one reviewed batch", "steps": [
      "Ingest the update, match every material line it touches",
      "Recompute every affected item under your sold-hour model",
      "Total the price and margin delta across the whole batch",
      "Flag anything past your tolerance for a closer look",
      "A human approves the batch — it's reversible"]}},
  {"vo": "The AI never changes a customer-facing price on its own. Every recompute is a proposal — old price, new price, the delta — until a person approves it.",
   "scene": "photo_overlay", "c": {"photo": P("agent_review"), "overlay": "booked", "title": "Approved — written back to ServiceTitan", "sub": "Human-approved, every time"}},

  # ---- CH6: worked example ----
  {"vo": "Here's what that actually looks like on one real vendor increase. These numbers are illustrative — built to show the mechanism, not a client result.",
   "scene": "chapter", "c": {"num": "06", "title": "One vendor increase, worked through"}},
  {"vo": "A three-quarter inch copper coupling moves from twenty dollars twenty-five cents to twenty-four twenty-five. Four twenty-five per unit, on the vendor's schedule, not yours.",
   "scene": "stat", "c": {"value": "+$4.25", "label": "The trigger: one copper coupling's vendor cost moves", "source": "illustrative"}},
  {"vo": "That one material is built into fourteen different service and assembly items across the book. Fourteen prices need to move — and Pricebook Connect only flagged the material, not the fourteen.",
   "scene": "stat", "c": {"value": "14 items", "label": "Service and assembly items built on that one material line", "source": "illustrative"}},
  {"vo": "The recompute sorts them: eleven are routine, small moves, grouped for a fast approval. Three are bigger assemblies with a real margin swing, flagged for a closer look before anyone signs off.",
   "scene": "stat", "c": {"value": "11 routine · 3 flagged", "label": "One reviewed batch instead of fourteen separate manual lookups", "source": "illustrative"}},

  # ---- CH7: comparison ----
  {"vo": "Question seven. How does this actually compare — manual review, Pricebook Pro and Connect together, and the agent?",
   "scene": "chapter", "c": {"num": "07", "title": "Side by side"}},
  {"vo": "Manual review has no cost-delta signal at all. Pro and Connect together surface the one material's delta. Only the agent recomputes every affected item and totals the margin impact before you approve.",
   "scene": "compare", "c": {"title": "Keeping the book current after a vendor increase", "cols": ["Manual", "Pricebook Pro + Connect", "Top Builder AI Pricebook agent"],
     "rows": [("Cost delta surfaced per material", [False, True, True]),
              ("Recomputes every affected service price", [False, False, True]),
              ("Totals the margin-dollar impact before approval", [False, False, True]),
              ("Flags out-of-tolerance items for review", [False, False, True]),
              ("Writes changes without your approval", [False, False, False])]}},
  {"vo": "None of this replaces Pricebook Pro or Connect. Pro's content library and Connect's vendor sync both still do a real job. The agent sits on top and does the recompute work neither one does.",
   "scene": "define", "c": {"eyebrow": "Not a replacement", "term": "Sits on top", "body": "Pro + Connect keep the book stocked. The agent recomputes what changes when a vendor cost moves"}},

  # ---- CH8: safety ----
  {"vo": "Question eight. What will the agent never do without your approval?", "scene": "chapter", "c": {"num": "08", "title": "Safe by design"}},
  {"vo": "No automatic price writes, ever. No invented costs or margins — every number comes from your actual pricebook and the vendor's actual update. Your rate and markup are inputs it reads, never values it changes on its own.",
   "scene": "secure", "c": {"title": "What never happens without you", "items": [
       ("✅", "No automatic writes", "Every batch is a proposal until a human approves it"),
       ("🔒", "No invented numbers", "Deterministic, tested code — the AI only explains it"),
       ("↩", "Reversible", "Any approved batch can be undone back to the prior price")]}},

  # ---- CH9: connects to the rest of the back office ----
  {"vo": "Question nine. How does this connect to the rest of the back office?", "scene": "chapter", "c": {"num": "09", "title": "One brain, not a separate tool"}},
  {"vo": "The same margin-delta data feeds the Financial agent's job-costing. A vendor increase absorbed this week shows up in this month's margin picture — instead of getting discovered at quarter-end, when a forty-percent job has quietly been running at thirty-one.",
   "scene": "split_photo", "c": {"photo": P("back_office"), "eyebrow": "Same data, one brain", "title": "Repricing feeds job costing", "sub": "This month's margin picture, not a quarter-end surprise"}},

  # ---- CH10: before/after + CTA ----
  {"vo": "So here's the actual shift.", "scene": "chapter", "c": {"num": "10", "title": "What changes"}},
  {"vo": "You go from a pricebook that quietly drifts behind every vendor increase, to one reviewed batch, on your schedule, every time a cost moves — with the margin impact already totaled for you.",
   "scene": "before_after", "c": {"before": P("before_stress"), "after": P("after_calm"), "caption": "Drifting behind every increase → one reviewed batch, every time"}},
  {"vo": "Your techs quote with confidence, because the price on the tablet reflects what the job costs today, not what it cost when the book was last touched.",
   "scene": "split_photo", "c": {"photo": P("handshake"), "eyebrow": "The outcome", "title": "Quote with confidence", "sub": "Today's costs, on every ticket"}},
  {"vo": "If you've never traced one vendor cost change all the way through to every service item it touches, that's exactly what a fit call walks through, on a real page from your own pricebook.",
   "scene": "cta", "c": {"eyebrow": "Top Builder AI · for ServiceTitan contractors", "title": "See it run against your pricebook", "sub": "Read the full guide, then book a 30-minute fit call", "url": "topbuilderai.com/blog"}},
]

if __name__ == "__main__":
    secs = ae.render_body(B, str(OUT), CACHE)
    print(f"BODY {secs:.1f}s ({secs/60:.1f} min), {len(B)} beats -> {OUT}")
