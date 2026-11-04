"""VALUE VIDEO — 6 Housecall Pro alternatives: which one actually gives you job costing you can
trust? (INFORMATIONAL, sourced, NO PRICE). Companion long-form to
landing/blog/housecall-pro-alternatives-job-costing-crews-under-15.html. Same sourced facts, framed
WITHOUT dollar figures per the hard price-guard rule (Cory 2026-07-29): Housecall Pro's own pricing
page names job costing on its cheapest (Basic) tier; Jobber's own pricing page gates Job Costing
behind Grow (third of four tiers), Automated Job Costing behind Plus (top tier); Service Fusion's own
pricing page sells job costing as a paid add-on on its entry (Starter) tier and makes it standard at
Plus, with an unlimited-user model instead of Jobber's per-seat pricing; Workiz and FieldPulse route
every plan to a sales call / custom quote and don't name job costing on their own pricing pages;
ServiceTitan is the enterprise tier this comparison is scoped below; all six vendors' QuickBooks sync
moves invoices/payments/customers, never the job-cost calculation itself. Adapted from
vid_jobber_vs_housecall_pro.py's proven shape (image-free scenes throughout — hook/chapter/define/
stat/process/checklist/cta — no missing-asset risk), with every dollar figure stripped and replaced
with tier names/ordinals so the price guard has nothing to catch. Renders animated body only.
Usage: python vid_housecall_pro_alternatives_job_costing.py
"""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)

CACHE = HERE / "build/val_hcp_alternatives_jobcosting"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = pathlib.Path("C:/Users/you/Downloads/ServiceTitan Agent platform/assets/video/longform/housecall-pro-alternatives-job-costing/body.mp4")

B = [
    # ---------- HOOK ----------
    {"vo": "You're running Housecall Pro, and its own pricing page already says it tracks job costs on your cheapest plan. So why can't you still answer whether last week's biggest job actually made money? Because a job-costing checkbox and a job-costing number you'd trust enough to act on the same week are two different things, and which alternative actually closes that gap depends on which tier you're really comparing, not which tool has the flashier features page. I checked six vendors' own current pricing pages, Housecall Pro, Jobber, Service Fusion, Workiz, FieldPulse, and ServiceTitan, to find exactly where job costing turns real on each one, and what's still missing even after it does.", "scene": "hook",
     "c": {"icon": "🧰", "title": "6 Housecall Pro Alternatives:\nWhich One Actually Has Job Costing?", "sub": "What each vendor's own pricing page says, tier by tier", "pulse": True}},

    # ---------- CH1 — does HCP even have it ----------
    {"vo": "First: does Housecall Pro even have job costing, or is that the wrong question entirely?", "scene": "chapter", "c": {"num": "01", "title": "Does Housecall Pro even have job costing?"}},
    {"vo": "It already does, per Housecall Pro's own pricing page, on its cheapest published plan, Basic. The page names the feature directly: track and report the costs associated with each job. So \"does Housecall Pro have job costing\" isn't actually the question worth asking. It's already a yes, on the lowest tier Housecall Pro sells, one user included.", "scene": "define",
     "c": {"eyebrow": "Already a yes, on the cheapest tier", "term": "Housecall Pro's own pricing page", "body": "\"Track and report the costs associated with each job\" — named on Basic, the entry plan, not gated to a higher tier."}},

    # ---------- CH2 — the real question ----------
    {"vo": "So what's the real question, if job costing already exists on the cheapest plan?", "scene": "chapter", "c": {"num": "02", "title": "What's the real question, then?"}},
    {"vo": "How granular that number gets as a crew grows past one truck, and whether the tool it lives in actually connects to the books your CPA opens. That's the split every one of these six vendors falls on differently, and it's the split this comparison is actually built around.", "scene": "define",
     "c": {"eyebrow": "Not existence — granularity", "term": "The question that actually changes what you pay", "body": "Which tier turns the checkbox into a number an owner trusts. Not whether the checkbox exists."}},

    # ---------- CH3 — Jobber ----------
    {"vo": "Start with Jobber. Where does job costing actually sit in its lineup?", "scene": "chapter", "c": {"num": "03", "title": "Where does Jobber put job costing?"}},
    {"vo": "Two tiers up from the entry plan. Jobber's own pricing page reserves job costing for its Grow tier, the third of four plans it sells. The two cheapest plans, Core and Connect, don't have a job-costing screen at all, no matter how long a shop's been a customer. Plus, the top tier, adds automated job costing with less manual data entry on top of that.", "scene": "stat",
     "c": {"value": "3rd of 4 tiers", "label": "Job Costing first appears on Jobber's third plan, Grow — the two cheaper tiers below it have no job-costing screen at all", "source": "Jobber's own pricing page"}},
    {"vo": "What that actually means for a shop sizing Jobber against Housecall Pro's entry-level plan:", "scene": "checklist",
     "c": {"title": "Jobber's job-costing ladder", "items": ["Core and Connect, the two cheapest tiers, have no job costing at all", "Grow, the third tier, adds manual job costing", "GPS tracking ships on every Jobber tier — job costing does not", "Plus, the top tier only, adds automated job costing with less hand-entry"]}},

    # ---------- CH4 — Service Fusion ----------
    {"vo": "Now Service Fusion. Does it gate job costing the same way Jobber does?", "scene": "chapter", "c": {"num": "04", "title": "How does Service Fusion price job costing?"}},
    {"vo": "No, it prices it differently, as a paid add-on at its entry tier instead of a feature a shop simply doesn't have. Per Service Fusion's own pricing page, the Starter plan includes unlimited users with QuickBooks Online and Desktop sync built in, and offers job costing as an optional add-on. It only becomes a standard, included feature one tier up, at Plus.", "scene": "define",
     "c": {"eyebrow": "An add-on, not a locked door", "term": "Service Fusion's Starter tier", "body": "Unlimited users, QuickBooks Online and Desktop sync built in, job costing available as a paid add-on. Standard at the next tier up, Plus."}},
    {"vo": "The real differentiator against Jobber isn't the add-on structure, it's the unlimited-user model underneath it. A three-technician crew and a fifteen-technician crew land on the same tier and the same feature set on Service Fusion. Jobber charges more per added seat on every one of its plans.", "scene": "stat",
     "c": {"value": "Unlimited users", "label": "Service Fusion's per-tier model, versus Jobber charging more for every added seat on any plan", "source": "Service Fusion's own pricing page"}},

    # ---------- CH5 — Workiz / FieldPulse ----------
    {"vo": "What about Workiz and FieldPulse — where do they actually land?", "scene": "chapter", "c": {"num": "05", "title": "Where do Workiz and FieldPulse land?"}},
    {"vo": "Neither one publishes a number at all. Both vendors' own pricing pages route every plan, Workiz's Standard, Pro, and Ultimate, and FieldPulse's Essentials, Professional, and Enterprise, to a sales call or a custom-quote request instead of listing a figure. Both list QuickBooks Online sync as a standard feature across every tier. Neither one names job costing as a feature on its own pricing page.", "scene": "define",
     "c": {"eyebrow": "No public number, either tool", "term": "Workiz and FieldPulse's own pricing pages", "body": "Every plan routes to a sales call or custom quote. QuickBooks sync: standard, all tiers. Job costing: not named as a feature, either vendor."}},
    {"vo": "What that actually means for a shop trying to compare all six tools honestly:", "scene": "checklist",
     "c": {"title": "What \"custom quote\" actually costs a shop", "items": ["Two of six vendors won't share a number without a sales call", "A missing job-costing label doesn't prove the platform can't do it", "It does mean a shop can't verify the feature, or its real tier, without that call", "QuickBooks sync being universal on both makes it a non-differentiator here too"]}},

    # ---------- CH6 — methodology ----------
    {"vo": "How were these six tools even chosen for this comparison in the first place?", "scene": "chapter", "c": {"num": "06", "title": "How were these six tools chosen?"}},
    {"vo": "From what independent field-service comparison sources, Jobber's own competitor page, and the major review directories, most consistently name as Housecall Pro's direct competitive set for crews under roughly fifteen people, Jobber, Workiz, Service Fusion, and FieldPulse. We added the two ends of the spectrum a growing shop eventually lands on: ServiceTitan for the enterprise tier, and Top Builder AI for the reconciliation gap the other five leave to a bookkeeper. Every claim in this video traces to that vendor's own current pricing page, not a review site's summary of it.", "scene": "define",
     "c": {"eyebrow": "Six tools, one method", "term": "Every vendor's own current pricing page", "body": "The four direct competitors named by independent comparison sources, plus the enterprise tier and the reconciliation-layer tier a growing shop eventually compares against."}},

    # ---------- CH7 — ServiceTitan ----------
    {"vo": "Where does ServiceTitan fit into a comparison built around crews under fifteen techs?", "scene": "chapter", "c": {"num": "07", "title": "Where does ServiceTitan fit?"}},
    {"vo": "Past the point this comparison is even written for. ServiceTitan is enterprise-grade job costing, dispatch, and reporting, at enterprise-grade implementation time and contract terms, the tool most of these five actually get compared against once a shop has already outgrown this size bracket, not before it.", "scene": "define",
     "c": {"eyebrow": "The next bracket up, not this one", "term": "ServiceTitan", "body": "Enterprise-grade job costing and reporting, with enterprise-grade onboarding time and contract terms. Not the comparison a crew under fifteen techs is actually running."}},

    # ---------- CH8 — the pattern ----------
    {"vo": "So across five real field-service tools, what's actually the pattern?", "scene": "chapter", "c": {"num": "08", "title": "What's the pattern across all five?"}},
    {"vo": "Line them up and the split is obvious the moment you stop looking at feature checklists and start looking at tiers.", "scene": "process",
     "c": {"title": "Where each one actually sits", "steps": ["Housecall Pro names job costing on its cheapest plan", "Jobber gates it two tiers up, on Grow", "Service Fusion sells it as an add-on before making it standard", "Workiz and FieldPulse won't name a tier or a number without a call"]}},
    {"vo": "Five out of five sync with QuickBooks Online in some form. Zero out of five make job costing itself part of that sync. That's the split that actually matters here, not which vendor's checkbox happens to show up first on a pricing page.", "scene": "stat",
     "c": {"value": "5 sync, 0 include job cost", "label": "All five field-service tools sync to QuickBooks in some form — none of them sync the job-costing calculation itself", "source": "Each vendor's own QuickBooks-integration documentation"}},

    # ---------- CH9 — why it still doesn't match ----------
    {"vo": "So if QuickBooks sync is universal, why does that number still not match a shop's real books?", "scene": "chapter", "c": {"num": "09", "title": "Why doesn't the number match your real books?"}},
    {"vo": "Because every one of these platforms computes its job-cost figure from data entered inside its own field app, timesheets, labor rates, line items, entirely separate from the general ledger a CPA actually opens. The sync moves invoices and payments and new customer records. It doesn't move the cost calculation itself, on any of the five.", "scene": "define",
     "c": {"eyebrow": "The math never leaves the field app", "term": "Why the sync doesn't close the gap", "body": "Job cost is computed from the field app's own timesheets and line items. The QuickBooks sync moves invoices and payments — not that calculation."}},

    # ---------- CH10 — what to check ----------
    {"vo": "Before switching off Housecall Pro for any of these, what should an owner actually check first?", "scene": "chapter", "c": {"num": "10", "title": "What to check before you switch"}},
    {"vo": "Four things, before paying more for a tier anywhere on this list that claims better job costing.", "scene": "process",
     "c": {"title": "Four checks before you pay for a higher tier", "steps": ["Pull your job-cost report for your three most recent multi-day jobs", "Check it against what QuickBooks actually shows for labor and material cost on those jobs", "If the two don't match, ask why before switching — a new platform can reproduce the same sync gap", "Price the tier that actually includes job costing, not the entry tier, on whichever alternative you're evaluating"]}},

    # ---------- CH11 — the honest reason ----------
    {"vo": "What's the honest reason a shop actually leaves Housecall Pro, if the feature already exists on its cheapest plan?", "scene": "chapter", "c": {"num": "11", "title": "The honest reason shops actually switch"}},
    {"vo": "Granularity, not the presence of a checkbox. Shops moving to a higher Jobber tier, a higher Service Fusion tier, or something built specifically around this gap are almost always chasing per-technician labor burden, multi-day project cost rollups, or a margin number they trust enough to act on the same week, not the feature's existence on a pricing page.", "scene": "define",
     "c": {"eyebrow": "Not the checkbox — the trust", "term": "Why shops actually switch tools", "body": "Per-technician labor burden. Multi-day rollups. A margin number trusted enough to act on same-week. Not whether \"job costing\" appears on the page."}},

    # ---------- CH12 — where TBA fits ----------
    {"vo": "So where does Top Builder AI actually fit, against six tools that all already claim job costing in some form?", "scene": "chapter", "c": {"num": "12", "title": "Where Top Builder AI actually fits"}},
    {"vo": "Not as a seventh scheduling tool with its own job-costing screen. It's a dedicated Financial agent that reconciles a shop's real field-app data against its actual QuickBooks books into a per-job margin, the kind of number a bookkeeper currently has to build by hand at month-end, and an operator reviews and approves every recommendation before any of it is treated as final.", "scene": "define",
     "c": {"eyebrow": "A reconciliation layer, not a seventh tool", "term": "Top Builder AI's Financial agent", "body": "Reconciles the field app's job-cost data against real QuickBooks books into a per-job margin. Deterministic math. Operator reviews and approves every recommendation."}},
    {"vo": "What that actually means in practice, compared to every tool named so far:", "scene": "checklist",
     "c": {"title": "What this is, and isn't", "items": ["Not a self-serve monthly tier to compare against the six above", "Scoped per shop through a direct engagement, not a signup page", "Every number computed deterministically — never guessed by a model", "A person approves every recommendation before it's treated as final"]}},

    # ---------- CTA ----------
    {"vo": "So here's the fastest way to check this yourself tonight. Pull up your current job-costing report, wherever it lives, Housecall Pro, Jobber, or anything else on this list, next to your real QuickBooks profit-and-loss for the same month. If those two numbers don't agree, or you genuinely don't know because nobody's ever put them side by side, that's the gap this video just walked through, and exactly what a real reconciliation closes.", "scene": "cta",
     "c": {"eyebrow": "Put both numbers side by side, tonight", "title": "Does Your Job-Cost Number Match Your Real Books?", "sub": "Most shops have never checked — a fit call walks through what turns up in yours", "url": "topbuilderai.com"}},
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
