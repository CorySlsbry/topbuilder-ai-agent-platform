"""VALUE VIDEO — How long does switching off your current field software actually take?
(INFORMATIONAL, sourced, NO PRICE). Companion long-form to
landing/blog/switching-contractor-software-quickbooks-migration-time.html. Same sourced facts as the
blog (Rework's SaaS buying framework guide, SaasAnt's QuickBooks Online export guide, Maximor's Finance
AI Adoption Benchmarking Report via Journal of Accountancy, insightsoftware's 2026 AI-adoption-in-finance
research), framed WITHOUT any dollar figures per the hard price-guard rule (Cory 2026-07-29): Top Builder
AI's own published pricing lives on the blog + site only, never in a video. Adapted from
vid_housecall_pro_alternatives_job_costing.py's proven shape (image-free scenes throughout — hook/
chapter/define/stat/process/checklist/cta — no missing-asset risk). Renders animated body only.
Usage: python vid_switching_contractor_software.py
"""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)

CACHE = HERE / "build/val_switching_contractor_software"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = pathlib.Path("C:/Users/you/Downloads/ServiceTitan Agent platform/assets/video/longform/switching-contractor-software-quickbooks-migration-time/body.mp4")

B = [
    # ---------- HOOK ----------
    {"vo": "You already know your current field software isn't working for you. So why haven't you switched yet? Because everyone remembers a migration horror story, not the software itself. I pulled the real industry timelines, what actually happens to your QuickBooks history when you export it, and the one thing almost every sales call leaves out about how long switching really takes.", "scene": "hook",
     "c": {"icon": "⏱️", "title": "How Long Does Switching\nField Software Actually Take?", "sub": "Real industry timelines, sourced, no sales-call spin", "pulse": True}},

    # ---------- CH1 — how long does it take ----------
    {"vo": "First question: how long does switching contractor software actually take, start to finish?", "scene": "chapter", "c": {"num": "01", "title": "How long does switching actually take?"}},
    {"vo": "It depends almost entirely on how much data has to move, not on how complicated the new software looks. Per Rework's SaaS buying framework guide, a smaller tool typically lands in four to six weeks elapsed from kickoff to go-live. A mid-market platform with tens of thousands of records and several integrations runs ten to twelve weeks to go-live, plus another two to four weeks of stabilization after that.", "scene": "stat",
     "c": {"value": "4–6 weeks", "label": "Typical elapsed time for a small-business tool switch, kickoff to go-live — a mid-market platform runs 10–12 weeks plus stabilization", "source": "Rework's SaaS buying framework guide"}},
    {"vo": "A one-or-two-truck shop switching field software sits closer to the small end of that range by record count alone. Which is exactly why a multi-month migration quoted for that size of business is a red flag, not a sign of thoroughness.", "scene": "define",
     "c": {"eyebrow": "Record count decides the timeline, not complexity", "term": "Where a small shop actually lands", "body": "Closer to the 4–6 week end of the range by data volume alone. A multi-month quote for that size shop should raise questions, not confidence."}},

    # ---------- CH2 — why longer than promised ----------
    {"vo": "So why do most software switches take longer than the sales call promised in the first place?", "scene": "chapter", "c": {"num": "02", "title": "Why longer than the sales call promised?"}},
    {"vo": "Because the sales call prices the software, not the migration. Per the same Rework guide, training costs are the single largest real switching cost, ahead of the software itself, followed by the cost of migrating and cleaning the actual data. Smaller organizations spend proportionally the most of anyone on that data step.", "scene": "define",
     "c": {"eyebrow": "The sales call prices the wrong thing", "term": "What actually drives switching cost", "body": "Training first, then data migration and cleaning — both ahead of the software's own price tag in Rework's cost ranking."}},
    {"vo": "And here's the sobering number behind that: roughly seventy percent of SaaS migrations fail to deliver the expected savings on a three-year basis. That gap traces back to underestimating the data step at the sales stage, not the new software being worse.", "scene": "stat",
     "c": {"value": "~70%", "label": "Of SaaS migrations fail to deliver the expected savings on a three-year basis — traced to underestimating data migration at the sales stage", "source": "Rework's SaaS buying framework guide"}},

    # ---------- CH3 — QuickBooks history ----------
    {"vo": "Now the part almost nobody asks about up front: what actually happens to your QuickBooks history when you switch platforms?", "scene": "chapter", "c": {"num": "03", "title": "What happens to your QuickBooks history?"}},
    {"vo": "It doesn't come along cleanly by default. Per SaasAnt's own QuickBooks Online export guide, some transactions and lists may not export fully, and the data that does export may need additional cleanup before it's usable. That's Intuit's own native export tool talking, not a competitor's complaint about it.", "scene": "define",
     "c": {"eyebrow": "Straight from QuickBooks' own export guide", "term": "\"Some transactions and lists may not export fully\"", "body": "Exported data may require additional cleanup before it's usable. That's why plain export-and-import rarely survives a real trial balance intact."}},
    {"vo": "A contractor with years of job history, customer records, and vendor bills sitting in QuickBooks should treat \"export\" as a starting point that needs verification, not a finished migration.", "scene": "checklist",
     "c": {"title": "What \"exporting your QuickBooks data\" actually gets you", "items": ["A starting point, per QuickBooks' own export guide — not a finished migration", "Some transactions and lists may not export fully", "Additional cleanup is expected, not a sign something went wrong", "This is why dedicated migration tools and done-for-you services exist at all"]}},

    # ---------- CH4 — the CPA ----------
    {"vo": "Here's a question that quietly kills a lot of switching decisions before they even start: can your CPA keep working the same way after you switch?", "scene": "chapter", "c": {"num": "04", "title": "Can your CPA keep working the way they already do?"}},
    {"vo": "Yes, if the platform is actually built for it instead of treating the accountant as an afterthought. Top Builder AI's own QuickBooks bridge includes an Accountant Sync that pushes a one-way feed straight into the CPA's existing QuickBooks account, so the accountant never has to log into a new system or re-learn a chart of accounts.", "scene": "define",
     "c": {"eyebrow": "The CPA never changes tools", "term": "Accountant Sync", "body": "A one-way feed into the CPA's own existing QuickBooks account. Same login, same chart of accounts, same filing cadence they already run."}},
    {"vo": "That one design decision removes what's often the real veto power in a switching decision. A CPA who refuses to change tools can keep using the one they already know, on the exact same cadence, while the contractor runs the field side somewhere better suited to it.", "scene": "checklist",
     "c": {"title": "Why the CPA objection usually kills the switch", "items": ["A CPA who won't change tools has an effective veto over the decision", "Accountant Sync removes the objection instead of arguing with it", "The books \"leave with you, always\" — the CPA keeps their own login", "No re-training, no new chart of accounts, no change to their filing cadence"]}},

    # ---------- CH5 — AI trust ----------
    {"vo": "The question underneath all of this: is AI going to mess up the books if it's touching the ledger at all?", "scene": "chapter", "c": {"num": "05", "title": "Is AI going to mess up the books?"}},
    {"vo": "That fear is reasonable, and finance professionals share it broadly. Which is exactly why the honest answer is that AI should never be doing the math in the first place. Two-thirds of one hundred CFOs surveyed said human oversight of agentic AI in finance is extremely or very critical to ensuring accuracy.", "scene": "stat",
     "c": {"value": "2 of 3 CFOs", "label": "Say human oversight of agentic AI in the finance function is extremely or very critical to ensuring accuracy", "source": "Maximor's Finance AI Adoption Benchmarking Report, via Journal of Accountancy"}},
    {"vo": "Separately, sixty percent of finance professionals point to stronger guardrails and clearer governance as what would actually build their confidence, and seventy-five percent say being able to see why a number came out the way it did would increase confidence further.", "scene": "stat",
     "c": {"value": "60% / 75%", "label": "Want stronger guardrails and governance / say explainable AI would increase their confidence in it", "source": "insightsoftware's 2026 AI-adoption-in-finance research"}},
    {"vo": "The right architecture answers that directly instead of arguing with it. Deterministic, tested code computes every number. The AI's only job is narrating the result in plain business language, with a person approving every change before anything posts to the ledger.", "scene": "define",
     "c": {"eyebrow": "The split that actually matters", "term": "Deterministic math, AI narrates", "body": "Tested code computes every figure. AI explains it in plain English. A person approves every change before it posts. If a platform can't explain that split, that's the real thing to worry about."}},

    # ---------- CH6 — what migrating actually involves ----------
    {"vo": "So what does actually migrating into a platform like this involve, day to day?", "scene": "chapter", "c": {"num": "06", "title": "What does migrating actually involve?"}},
    {"vo": "Two separate tracks, handled differently on purpose. The QuickBooks side is a deterministic migration: the incoming trial balance is checked per account against QuickBooks to the penny, and any difference is itemized rather than absorbed into a rounding line.", "scene": "define",
     "c": {"eyebrow": "Track one — the books", "term": "Penny-verified, per account", "body": "The incoming trial balance is checked account by account against QuickBooks. Any difference is itemized, never quietly rounded away."}},
    {"vo": "Pulling job and cost history out of ServiceTitan, Jobber, or a similar field platform is handled as a done-for-you migration by a real person, not an automated self-serve import button. That's deliberate, not a missing feature: a fully automated field-data import risks folding years of job-level detail into one lump-sum opening balance that nobody, including the CPA, ever actually sees itemized.", "scene": "define",
     "c": {"eyebrow": "Track two — the field data", "term": "Done-for-you, by a person", "body": "Job and cost history from ServiceTitan or Jobber is migrated by a real person, on purpose — so nothing gets folded into a lump sum nobody, including the CPA, ever sees itemized."}},

    # ---------- CH7 — four checks before switching ----------
    {"vo": "Before switching off anything on this list, what should an owner actually check first?", "scene": "chapter", "c": {"num": "07", "title": "Four checks before you switch"}},
    {"vo": "Four things, before paying for a switch anywhere, no matter which platform you're evaluating.", "scene": "process",
     "c": {"title": "Four checks before you switch", "steps": ["Pull your current QuickBooks trial balance before anything else moves", "Decide what field-platform history actually needs to travel — recent job costs matter far more than five-year-old closed jobs", "Confirm the CPA's access path before go-live, not after", "Get the itemized diff report before trusting the opening balance a migration hands you"]}},

    # ---------- CH8 — the honest reason ----------
    {"vo": "So what's the honest reason a shop actually goes through with a switch, once you strip out the sales-call promises?", "scene": "chapter", "c": {"num": "08", "title": "The honest reason shops actually switch"}},
    {"vo": "It's never really the software's feature list. It's a books number an owner can trust enough to act on the same week, a CPA who doesn't have to change how they work, and an AI layer that explains itself instead of asking to be trusted blindly. Every one of those is a migration-quality question, not a software-feature question.", "scene": "define",
     "c": {"eyebrow": "Not the feature list — the trust", "term": "What actually decides a switch", "body": "A number you trust enough to act on. A CPA who doesn't have to change tools. An AI that explains itself. All three are migration questions, not feature questions."}},

    # ---------- CTA ----------
    {"vo": "So here's the fastest way to check this for yourself tonight. Pull your current QuickBooks trial balance, and ask whoever you're evaluating to show you an itemized diff report, not just a green checkmark that says migration complete. If they can't show you that, that's the actual answer to how long — and how safely — this is really going to take.", "scene": "cta",
     "c": {"eyebrow": "Ask for the itemized diff, not a checkmark", "title": "How Long Would Your Migration Really Take?", "sub": "A fit call walks through your trial balance and a real week-by-week plan for your shop", "url": "topbuilderai.com"}},
]

# Graceful degradation: if a still failed to generate, swap its beat to a text scene so the render never dies.
for b in B:
    c = b.get("c", {})
    if b["scene"] in ("photo", "split_photo", "photo_overlay") and not pathlib.Path(c.get("photo", "")).exists():
        print("MISSING IMAGE -> degrade to define:", c.get("photo"))
        b["scene"] = "define"
        b["c"] = {"eyebrow": c.get("eyebrow", ""), "term": c.get("title", ""), "body": c.get("sub", "")}

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    secs = ae.render_body(B, OUT, CACHE)
    print(f"BODY {secs:.1f}s ({secs/60:.1f} min), {len(B)} beats -> {OUT}")
