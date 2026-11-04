"""VALUE VIDEO — The Best ServiceTitan Alternative for Small Trades Crews (INFORMATIONAL).
Pure value, no pitch until the very end. Companion to
landing/blog/best-servicetitan-alternative-small-trades-job-costing.html — same sourced facts,
same honest framing (ServiceTitan is enterprise-sized; Jobber/Housecall Pro punt job costing to
QuickBooks; Top Builder OS unifies both for a 1-10 person shop).
Renders the CHAPTER BODY only — the hook and CTA are separate single-beat clips
(vid_st_alt_small_trades_intro.py / _outro.py) assembled around this body by render_longform.py.
Usage: python vid_st_alt_small_trades_body.py
"""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)

LIB = pathlib.Path(r"C:\Users\you\.geo-flywheel\asset-library\top-builder-ai\image")
CACHE = HERE / "build/val3_stalt"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = pathlib.Path("C:/Users/you/Downloads/ServiceTitan Agent platform/assets/video/longform/st-alt-small-trades/body.mp4")
def P(n): return str(LIB / n)

B = [
    # ---------- CH1 — the size mismatch ----------
    {"vo": "ServiceTitan is a genuinely excellent platform for the business it is built for, which is an established, multi-technician operation. It is priced and sized for an established, multi-technician operation on an annual enterprise contract, with a significant upfront implementation and weeks to months of configuration before go-live.", "scene": "chapter", "c": {"num": "01", "title": "The size mismatch"}},
    {"vo": "None of that is a scandal. It is what enterprise field-service software costs and takes. The mismatch is buying it as a two or three truck shop, paying enterprise rates for dispatch and inventory depth you will mostly never touch, and spending months onboarding a system sized for a business three times yours.", "scene": "photo",
     "c": {"photo": P("st-alternative-hero.png"), "eyebrow": "Right tool, wrong size", "title": "Enterprise depth, small-shop budget", "sub": "Built for 20-plus technicians, sold to a two-truck crew"}},
    {"vo": "The onboarding itself is a project — a significant upfront implementation and weeks to months of configuration before the system is even live.", "scene": "stat",
     "c": {"value": "Weeks to months", "label": "Typical enterprise onboarding before the system is even live", "source": "Independent ServiceTitan implementation guides, published 2026"}},

    # ---------- CH2 — where Jobber and Housecall Pro stop ----------
    {"vo": "So a small shop looks at Jobber or Housecall Pro instead, and they're good. They're built and priced for a small shop, and both are strong at scheduling, dispatch, quoting, and invoicing. If all you need is to book work and get paid, either is a reasonable pick.", "scene": "chapter", "c": {"num": "02", "title": "Where Jobber & Housecall Pro stop"}},
    {"vo": "But both hand accounting off to QuickBooks. Neither produces real job costing on its own. So the moment an owner wants to know what a specific job made after true labor and material cost, the answer lives in a different system, or a spreadsheet, or a bookkeeper's head. The field tool knows what you invoiced. It doesn't know what the job cost you.", "scene": "photo",
     "c": {"photo": P("right-sized-hero.png"), "eyebrow": "The wall both tools hit", "title": "It knows what you invoiced.\nNot what the job cost you.", "sub": "Job costing gets handed off to QuickBooks"}},

    # ---------- CH3 — why QuickBooks alone won't close the gap ----------
    {"vo": "The instinct is: field tool plus QuickBooks covers it. In practice it doesn't, because QuickBooks was built for general small-business accounting, not construction job costing.", "scene": "chapter", "c": {"num": "03", "title": "Why QuickBooks alone won't close it"}},
    {"vo": "It has no native work-in-progress schedule. No real cost-code structure to split a job into labor, materials, and subs. It doesn't track committed costs from open purchase orders, so a job can look profitable right up until the material bills land.", "scene": "checklist",
     "c": {"title": "What QuickBooks alone is missing", "items": ["No native work-in-progress (WIP) schedule", "No real cost-code structure", "No committed costs from open purchase orders", "No per-job true-cost view"]}},
    {"vo": "Shops paper over this with spreadsheets and a bookkeeper reconciling after the fact — which is exactly how what did this job make turns into a question answered three weeks late, if at all. It's not a QuickBooks failing so much as a category mismatch: a great general ledger being asked to do a job-costing job it was never designed for.", "scene": "photo",
     "c": {"photo": P("paperwork-hero.png"), "eyebrow": "The workaround", "title": "Spreadsheets and a bookkeeper, after the fact", "sub": "The question gets answered three weeks late, if at all"}},

    # ---------- CH4 — the comparison ----------
    {"vo": "Laid out side by side, the gap is the same one every time — real job costing and an owned set of books.", "scene": "chapter", "c": {"num": "04", "title": "Side by side"}},
    {"vo": "ServiceTitan has the depth, at enterprise pricing. Jobber and Housecall Pro are priced for a small shop, but punt job costing and the books to QuickBooks. A unified system carries the depth a small shop actually needs, at small-shop pricing.", "scene": "compare",
     "c": {"title": "What a small shop needs", "cols": ["ServiceTitan", "Jobber / HCP", "Top Builder OS"],
           "rows": [("Priced for a 1-10 person shop", [False, True, True]),
                    ("Real job costing, true burden", [True, False, True]),
                    ("Owned books + WIP + CPA pack", [False, False, True]),
                    ("Live day-one, no implementation fee", [False, True, True])]}},

    # ---------- CH5 — what real job costing means ----------
    {"vo": "So what does real job costing actually mean? Every hour and every part lands on the specific job, at its true cost, so profit is knowable per job instead of only per month.", "scene": "chapter", "c": {"num": "05", "title": "What real job costing means"}},
    {"vo": "The catch most software misses: the true cost of labor isn't the hourly wage. It's the burdened rate — wages, plus payroll taxes, plus workers' comp by class code, plus the overtime split at forty hours. A journeyman billed at his base wage looks cheaper than he is. Costed at his burdened rate, the job's real margin appears.", "scene": "define",
     "c": {"eyebrow": "The blind spot", "term": "The burdened labor rate", "body": "Wages, plus payroll taxes, workers' comp by class, and overtime past 40 hours — not just the hourly wage."}},
    {"vo": "Add materials posted to the job, committed costs pulled from open purchase orders before the bill even arrives, and actuals compared to the estimate — and the owner finally gets a straight answer to the only question that matters: what did this job make.", "scene": "stat",
     "c": {"value": "Per-job profit", "label": "True revenue minus true burdened labor and materials, the moment the job closes", "source": "Illustrative of the job-costing gap; actual figures are specific to each shop"}},

    # ---------- CH6 — what Top Builder OS does ----------
    {"vo": "Top Builder OS is one system a small trades shop runs the whole business on, front to back.", "scene": "chapter", "c": {"num": "06", "title": "What Top Builder OS does"}},
    {"vo": "Book the job onto a dispatch board. Build a good-better-best estimate with photos. Capture time and materials from the field at true burdened cost. Invoice with card and ACH. And underneath all of it, post every hour and dollar into an owned, double-entry ledger on the NAHB chart of accounts, with a one-click CPA hand-off pack.", "scene": "process",
     "c": {"title": "One system, front to back", "steps": ["Book and dispatch the job", "Estimate and invoice, in one place", "Cost every hour at true burden", "Post to owned, CPA-ready books"]}},
    {"vo": "Eight helper agents do the paperwork, and none of them ever move money without the owner approving it. Every figure is computed by deterministic, tested code — never guessed by an AI.", "scene": "photo",
     "c": {"photo": P("one-ledger-hero.png"), "eyebrow": "Same system, same ledger", "title": "The field data and the books,\nin one place", "sub": "Deterministic code computes every figure — never an AI guess"}},

    # ---------- CH7 — pricing ----------
    {"vo": "The pricing is deliberately the opposite of an enterprise contract: two flat monthly tiers, no per-seat charge, and no implementation fee. One tier covers up to ten people, the next up to twenty five, with unlimited users included.", "scene": "stat",
     "c": {"value": "Two flat tiers", "label": "Up to 10 or 25 people, unlimited users included, no per-seat charge", "source": "Top Builder OS current pricing"}},
    {"vo": "No add-on store, no implementation fee, no per-technician pricing — so hiring your next tech never changes the bill. Month-to-month, no cancellation fee, and your books export with one click forever, whether you stay or leave.", "scene": "checklist",
     "c": {"title": "No enterprise contract, on purpose", "items": ["No implementation fee, no per-tech pricing", "Month-to-month, no cancellation fee", "One-click book export, forever", "A free seat for your CPA or bookkeeper"]}},

    # ---------- CH8 — when ServiceTitan is still right ----------
    {"vo": "To keep this honest: if the business is genuinely enterprise-shaped — twenty-plus technicians, multiple branches, high-volume commercial dispatch, the staff to run a deep platform — ServiceTitan's depth is real and worth paying for. The point isn't that ServiceTitan is bad. It's that a two to ten person shop is a different business, not a miniature enterprise, and deserves software built for what it actually is.", "scene": "define",
     "c": {"eyebrow": "The honest exception", "term": "When ServiceTitan is still the right call", "body": "20-plus technicians, multiple branches, high-volume commercial dispatch — that depth is worth paying for at that scale."}},

    # ---------- CH9 — keeping your accountant happy ----------
    {"vo": "Switching systems terrifies contractors for one reason above all — breaking the relationship with their accountant and the QuickBooks history they've built. A penny-verified migration in, a one-way sync out so a CPA who lives in QuickBooks keeps getting clean journal entries, and a free seat for that CPA. Nobody has to be forced off the tool they trust for the switch to work.", "scene": "split_photo",
     "c": {"photo": P("two-systems-hero.png"), "eyebrow": "Keeping your accountant happy", "title": "Clean journal entries out,\nnot a shoebox", "sub": "The CPA keeps working the way they prefer"}},

    # ---------- CH10 — does it run payroll ----------
    {"vo": "Does Top Builder OS run payroll? No, and it doesn't pretend to. Payroll filing and any certified or prevailing-wage payroll stay with your existing payroll provider. What it does do is capture burdened labor per job — wages, plus payroll taxes, plus workers' comp by class, plus the overtime split at forty hours — so job costs are accurate, and the labor accrual clears cleanly through bank reconciliation. It costs your labor correctly on the job. It doesn't cut the checks or file the taxes.", "scene": "define",
     "c": {"eyebrow": "Where the line is drawn", "term": "Does it run payroll?", "body": "No — payroll stays with your provider. Top Builder OS costs the labor correctly on the job; it doesn't cut checks or file taxes."}},

    # ---------- CH11 — am I locked in ----------
    {"vo": "Is the data locked in if you switch? No. Billing is month to month with no cancellation fee, and your books export with one click, forever, whether you stay or go. The double-entry ledger is yours. The accountant sync and journal export mean you're never trapped inside a proprietary format — a direct answer to the biggest fear contractors have about leaving an incumbent, that the exit will be expensive or the data held hostage.", "scene": "checklist",
     "c": {"title": "Is your data locked in?", "items": ["Month-to-month, no cancellation fee", "One-click book export, forever", "The double-entry ledger is yours", "Never trapped in a proprietary format"]}},

    # ---------- CH12 — how fast to start ----------
    {"vo": "How long does it actually take to get started? There's no implementation fee and no multi-month onboarding. Top Builder OS is self-serve and live day one, seeded with a trade-specific pricebook and cost codes, so a plumber, electrician, HVAC, or roofing shop starts with sensible defaults instead of a blank system — a deliberate contrast with an enterprise platform where a large upfront implementation and weeks to months of configuration are considered normal.", "scene": "stat",
     "c": {"value": "Live day one", "label": "Self-serve, trade-specific pricebook pre-loaded — no implementation fee, no multi-month onboarding", "source": "Top Builder OS current onboarding"}},

    # ---------- CH13 — who it's actually built for ----------
    {"vo": "Who is this actually built for? The owner-operator and small crew — a roofer or an HVAC owner doing estimates at the kitchen table at eleven at night, while a spouse or a part-time bookkeeper wrestles the books. One to ten people, allergic to training and accounting jargon, who want to book work, run it, invoice it, and actually know what each job made, without a spreadsheet or a full-time bookkeeper on staff.", "scene": "photo",
     "c": {"photo": P("crew-phone-hero.png"), "eyebrow": "Who this is for", "title": "The owner-operator,\nnot the 20-tech operation", "sub": "One to ten people who want a straight answer, not a spreadsheet"}},

    # ---------- CH14 — the gut check ----------
    {"vo": "The gut check is simple. Are you buying capability you'll actually use, or capability that impresses on a demo and gathers dust? A small crew that wants to book work, run it, get paid, and finally know what every job made is describing one system — not an enterprise platform bolted to a spreadsheet.", "scene": "photo",
     "c": {"photo": P("owner-relief-hero.png"), "eyebrow": "The gut check", "title": "Capability you'll use.\nNot capability that impresses on a demo.", "sub": "One system, not an enterprise platform bolted to a spreadsheet"}},
]

# Graceful degradation: if a still failed to generate, swap its beat to a text scene so the render never dies.
for b in B:
    c = b.get("c", {})
    if b["scene"] in ("photo", "split_photo", "photo_overlay") and not pathlib.Path(c.get("photo", "")).exists():
        print("MISSING IMAGE -> degrade to define:", c.get("photo"))
        b["scene"] = "define"
        b["c"] = {"eyebrow": c.get("eyebrow", ""), "term": c.get("title", ""), "body": c.get("sub", "")}

if __name__ == "__main__":
    # NOTE 2026-07-29: Gemini's free-tier TTS quota (GenerateRequestsPerDayPerProjectPerModel,
    # limit 10/day) was exhausted mid-render after beats 0-8 cached under the full "blend" voice
    # (Gemini Charon -> ElevenLabs STS). Falling back to "eleven" (pure ElevenLabs TTS into Cory's
    # clone, voice_synth's own documented no-Gemini fallback) for the remaining beats only -- the
    # cache means beats 0-8 keep their blended audio; only 9+ use the plain-ElevenLabs path.
    OUT.parent.mkdir(parents=True, exist_ok=True)
    secs = ae.render_body(B, OUT, CACHE, voice="eleven")
    print(f"BODY {secs:.1f}s ({secs/60:.1f} min), {len(B)} beats -> {OUT}")
