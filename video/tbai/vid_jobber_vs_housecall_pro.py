"""VALUE VIDEO — Jobber vs Housecall Pro: which one actually shows you if a job made money?
(INFORMATIONAL, sourced). Companion long-form to
landing/blog/jobber-vs-housecall-pro-job-costing.html. Same sourced facts: Jobber's own pricing
page gates Job Costing behind the Grow plan (third of four tiers), Automated
Job Costing behind Plus (the top tier); Housecall Pro's own pricing page gates job costing behind
Essentials (middle of three tiers); Jobber's own Job Costing help article (labor x timesheet hours,
materials, expenses; double-count bug; no retroactive rate fix; no recurring-job reporting);
Housecall Pro's own Job Costing set-up guide (fully loaded rate incl. travel time, materials, misc,
commissions; no retroactive rate fix either); Jobber's own QuickBooks Integration FAQ + items-sync
article (clients/products/invoices/payments/timesheet HOURS only, no job costing, Jobber becomes
"source of truth" after initial import); Housecall Pro's own QuickBooks sync article (invoices,
payments, new customers, new price-book items only, no job costing, no estimates, manual delete
sync); Intuit's own QuickBooks Online Projects documentation (Plus/Advanced only, no auto-feed from
either platform). Adapted from vid_bookkeeper_access.py's proven shape — image-free scenes
throughout (hook/chapter/define/stat/process/checklist/cta), no missing-asset risk. Renders
animated body only. Usage: python vid_jobber_vs_housecall_pro.py
"""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)

CACHE = HERE / "build/val_jobber_vs_hcp"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = pathlib.Path("C:/Users/you/Downloads/ServiceTitan Agent platform/assets/video/longform/jobber-vs-housecall-pro/body.mp4")

B = [
    # ---------- HOOK ----------
    {"vo": "You picked Jobber or Housecall Pro, you're paying for it every month, and you still can't answer the one question that actually matters: did that last job make money? Both vendors sell a job-costing feature that promises to answer exactly that, but on both platforms it sits one paid tier above where most small crews actually live, and neither one's QuickBooks sync carries that profit number into the books your CPA opens. So let's go through exactly what each vendor's own documentation says their job-costing feature tracks, what actually moves into QuickBooks and what doesn't, and the one structural gap both of them leave open no matter which one you pick.", "scene": "hook",
     "c": {"icon": "💰", "title": "Jobber vs Housecall Pro: Does Either One Show True Job Profit?", "sub": "What each vendor's own pricing and job-costing docs actually say", "pulse": True}},

    # ---------- CH1 — Jobber pricing ----------
    {"vo": "First question: if you're already on Jobber, is job costing even part of your plan?", "scene": "chapter", "c": {"num": "01", "title": "Where does Jobber even put job costing?"}},
    {"vo": "Only if you're on the third of Jobber's four plans. Per Jobber's own pricing page, checked at the time this was written, the tiers run Core, Connect, Grow, and Plus, each stepping up in what it unlocks. Job Costing itself first appears on Grow, the third tier up. A shop on Core or Connect, the two entry plans, has no job-costing screen in Jobber at all, no matter how long they've been a customer.", "scene": "stat",
     "c": {"value": "3rd of 4 plans", "label": "Job Costing first appears on Jobber's third plan, Grow — Core and Connect below it have no job-costing screen at all", "source": "Jobber's own pricing page"}},
    {"vo": "And even Grow doesn't get you the full picture. Automated Job Costing, the version that captures line-item costs and logged expenses with less manual entry, is locked to Plus, the top plan. So there are really three tiers of Jobber user: no job costing at all, manual job costing on Grow, and automated job costing on Plus only, and the pricing page doesn't make that three-way split obvious at a glance.", "scene": "define",
     "c": {"eyebrow": "Three tiers, not two", "term": "Jobber's job-costing ladder", "body": "Core/Connect: none. Grow: manual job costing. Plus only: Automated Job Costing with less hand-entry."}},

    # ---------- CH2 — HCP pricing ----------
    {"vo": "Now flip to Housecall Pro. Same question — which plan actually unlocks job costing?", "scene": "chapter", "c": {"num": "02", "title": "Where does Housecall Pro put job costing?"}},
    {"vo": "The middle of its three plans. Per Housecall Pro's own pricing page, the tiers run Basic, Essentials, and MAX. The Essentials tier description states it lets a shop track and report the costs associated with each job, and that same tier is also where QuickBooks Online sync first shows up. A shop on the entry-level Basic plan gets online booking, invoicing, payments, and dispatch, but no job costing and no QuickBooks connection at all.", "scene": "stat",
     "c": {"value": "Middle of 3 plans", "label": "Housecall Pro's Essentials tier — the cheapest plan with both job costing AND QuickBooks Online sync, per Housecall Pro's own pricing page", "source": "Housecall Pro's own pricing page"}},

    # ---------- CH3 — what Jobber's job costing tracks ----------
    {"vo": "So you're paying for Grow or higher on Jobber. What does that job-costing screen actually calculate?", "scene": "chapter", "c": {"num": "03", "title": "What Jobber's job costing actually tracks"}},
    {"vo": "Three inputs, with profit as revenue minus total cost. Per Jobber's own Job Costing help article, labor cost comes from each employee's hourly labor rate, meant to include wage, benefits, and taxes, multiplied by their timesheet hours on that specific job. Material cost comes from line-item unit costs on the job. Expenses are whatever gets logged directly against it. None of that calculates itself — someone has to enter accurate rates and log every expense for the number to mean anything.", "scene": "define",
     "c": {"eyebrow": "Three inputs, revenue minus cost", "term": "Jobber's job-costing formula", "body": "Labor: rate x timesheet hours. Materials: line-item costs. Expenses: whatever's logged. All manually fed."}},
    {"vo": "And Jobber's own documentation admits real cracks in that number. A labor-rate change only applies to future timesheet hours, not any past ones, so old jobs never get recalculated after a raise. If a job has both a line-item cost on the quote and a separately logged expense for that same cost, Jobber's own docs say it currently counts both against profitability, a double-count that quietly understates margin. And job-cost reporting isn't available at all for recurring jobs, so a maintenance-plan customer's profitability never shows up in that report.", "scene": "checklist",
     "c": {"title": "Cracks Jobber's own docs admit to", "items": ["Rate changes don't fix past jobs — future timesheets only", "A cost can get counted twice — quote line-item AND logged expense", "Recurring jobs don't appear in job-cost reporting at all", "The number is only as accurate as what a person entered"]}},

    # ---------- CH4 — what HCP's job costing tracks ----------
    {"vo": "Housecall Pro's Essentials tier promises the same kind of answer. What does its version actually track?", "scene": "chapter", "c": {"num": "04", "title": "What Housecall Pro's job costing actually tracks"}},
    {"vo": "Five categories instead of three, with a profit-margin formula on top. Per Housecall Pro's own Job Costing set-up guide, it tracks labor at a fully loaded rate, meaning base hourly pay plus employer-paid taxes, insurance, and benefits, multiplied by time on the job including travel time. Then materials, miscellaneous expenses like permits or parking, commissions, and service line-item unit costs. Per its own Job Costing Reports article, profit margin is gross profit divided by job revenue, where gross profit subtracts every one of those categories combined.", "scene": "define",
     "c": {"eyebrow": "Wider than Jobber's, on paper", "term": "Housecall Pro's fully loaded rate", "body": "Base pay + employer taxes, insurance, benefits, x time on job INCLUDING travel. Five cost categories total."}},
    {"vo": "But it has the same retroactive blind spot Jobber does. Housecall Pro's own set-up guide states plainly that adding or updating an employee's labor rate after the fact will not retroactively update the labor costs already calculated on past jobs. A shop that raises pay mid-year and never rechecks old job-cost reports is looking at margin numbers built on stale, underpriced labor.", "scene": "stat",
     "c": {"value": "0 retroactive", "label": "Neither platform recalculates past jobs when a labor rate changes — Jobber's docs and Housecall Pro's docs both say so directly", "source": "Jobber's and Housecall Pro's own job-costing documentation"}},

    # ---------- CH5 — Jobber QBO sync ----------
    {"vo": "So Jobber computes a profit number inside the app. Does that number actually reach your QuickBooks file?", "scene": "chapter", "c": {"num": "05", "title": "Does Jobber's QuickBooks sync carry job cost over?"}},
    {"vo": "No. Per Jobber's own QuickBooks Integration FAQ, the sync moves clients, products and services, invoices, payments, and timesheets, one-way, from Jobber into QuickBooks Online. Job costing isn't on that list. And per Jobber's own items-sync article, that timesheet sync only moves total hours per team member, not a labor cost tied to any specific job. Your bookkeeper sees hours. She does not see what those hours cost against a particular invoice.", "scene": "checklist",
     "c": {"title": "What Jobber's QuickBooks sync actually moves", "items": ["Clients, products/services, invoices, payments", "Timesheet HOURS per employee — not labor cost per job", "Job costing — not on the list, per Jobber's own FAQ", "One-way only: Jobber → QuickBooks"]}},
    {"vo": "There's a subtler problem underneath that. Jobber's own Job Costing help article states that after an initial, one-time cost import from QuickBooks Online, quote, Jobber becomes the source of truth for costs, unquote. That means whatever Jobber's job-costing screen shows from that point forward can drift away from what QuickBooks actually reflects, with nothing in Jobber's own docs describing an ongoing, two-way reconciliation between the two numbers.", "scene": "define",
     "c": {"eyebrow": "A one-time import, then drift", "term": "\"Jobber becomes the source of truth\"", "body": "Jobber's own words. After the initial import, the two systems' cost numbers can diverge with no reconciliation."}},

    # ---------- CH6 — HCP QBO sync ----------
    {"vo": "Same question for Housecall Pro. Does its Essentials-tier job costing make it into QuickBooks?", "scene": "chapter", "c": {"num": "06", "title": "Does Housecall Pro's QuickBooks sync carry job cost over?"}},
    {"vo": "Also no. Per Housecall Pro's own help article on syncing to QuickBooks Online, the integration moves invoices, payments, new customer records, and new price-book items, one-way, into QuickBooks. Job costing and labor costs don't appear anywhere in that list. The same article notes estimates never transfer to QuickBooks Online at all, and anything deleted or canceled inside Housecall Pro has to be deleted separately, by hand, on the QuickBooks side.", "scene": "stat",
     "c": {"value": "0 of 5", "label": "None of Housecall Pro's five job-costing categories — labor, materials, misc, commissions, line items — appear in its QuickBooks sync, per its own help article", "source": "Housecall Pro's own QuickBooks-sync help article"}},
    {"vo": "So a shop can build a fully loaded, travel-time-inclusive labor rate report inside Housecall Pro's Essentials plan, and not one dollar of that labor cost, material cost, or resulting profit figure ever reaches the QuickBooks file the CPA actually opens at tax time.", "scene": "define",
     "c": {"eyebrow": "The number lives in one app only", "term": "Essentials-tier job costing", "body": "Built inside Housecall Pro. Never syncs. The CPA's QuickBooks file never sees it."}},

    # ---------- CH7 — the shared gap ----------
    {"vo": "So both vendors build their own job-costing screen, and neither one connects it to QuickBooks. Is that a coincidence, or a pattern?", "scene": "chapter", "c": {"num": "07", "title": "The gap both platforms actually share"}},
    {"vo": "It's a pattern, not a coincidence, and not unique to these two. Both platforms compute per-job profit from data entered inside their own field app, timesheets, labor rates, line items, and that number never lands in the one place a shop's actual books, tax return, and CPA all live. This blog has documented the same structural gap across ServiceTitan, Buildertrend, and Service Fusion in a companion piece on QuickBooks sync gaps. It's an industry-wide pattern in field-service software, not a Jobber or Housecall Pro-specific problem.", "scene": "checklist",
     "c": {"title": "Why this isn't a Jobber-or-HCP-specific flaw", "items": ["ServiceTitan, Buildertrend, Service Fusion show the same pattern", "Field apps compute cost from their OWN entered data", "Neither vendor syncs that cost number to QuickBooks", "The books your CPA opens never see the field app's math"]}},

    # ---------- CH8 — QBO Projects ----------
    {"vo": "QuickBooks itself has a feature built to hold job-level cost. Does that fix it?", "scene": "chapter", "c": {"num": "08", "title": "Can QuickBooks Online Projects fix this?"}},
    {"vo": "It's the right feature, but it comes with two catches. Per Intuit's own help documentation, QuickBooks Online Projects requires the Plus or Advanced plan, an extra cost on top of whatever Jobber or Housecall Pro already charges. And neither Jobber's nor Housecall Pro's own integration docs describe automatically feeding time entries or labor cost into a QuickBooks Online Project. Even a shop already paying for Projects still has to build that bridge by hand, job by job.", "scene": "define",
     "c": {"eyebrow": "Built for this, but not connected", "term": "QuickBooks Online Projects", "body": "Requires Plus or Advanced. Neither Jobber nor Housecall Pro auto-feeds time or labor cost into it."}},

    # ---------- CH9 — side by side ----------
    {"vo": "Put both platforms side by side. Where does each one actually come out ahead?", "scene": "chapter", "c": {"num": "09", "title": "Jobber vs Housecall Pro, side by side"}},
    {"vo": "On raw cost categories, Housecall Pro tracks more: five, including commissions and travel time in the labor rate, against Jobber's three. On which tier gets you there, Jobber unlocks job costing one plan earlier in its lineup than Housecall Pro does in its own. On QuickBooks sync depth, they're functionally tied at zero — neither moves job costing, and Housecall Pro's sync additionally skips estimates entirely, something Jobber's sync does include.", "scene": "process",
     "c": {"title": "Where each one actually wins", "steps": ["Cost categories tracked — Housecall Pro: 5, Jobber: 3", "Job costing unlocks one tier earlier — Jobber's Grow", "QuickBooks sync depth for job cost — tied at zero, both", "Estimates syncing to QuickBooks — Jobber only"]}},
    {"vo": "Neither platform wins on the question that actually matters to an owner staring at a bank balance: does the profit number I'm looking at match what my books say. On that specific question, both platforms land in exactly the same place, because both built their job-costing math to live and die inside their own field app.", "scene": "stat",
     "c": {"value": "Tied at 0", "label": "On the one question that matters — does the job-cost number match your real QuickBooks books — both platforms land in the same place", "source": "Jobber's and Housecall Pro's own QuickBooks-sync documentation"}},

    # ---------- CH10 — mobile field use ----------
    {"vo": "One more practical question before the comparison — can a crew actually use either app in the field without calling the office?", "scene": "chapter", "c": {"num": "10", "title": "What actually works from the field"}},
    {"vo": "For scheduling and payment, yes, on both. Housecall Pro's own mobile app page confirms offline access to schedules and job details, plus in-field card, check, and financing payments. Jobber's own mobile app page confirms clock in and out, job details, quotes, and auto-generated invoices from the field. What neither vendor's mobile app page documents in detail is in-field material-cost or job-cost entry — the exact data that feeds the job-costing screen this whole video is about.", "scene": "checklist",
     "c": {"title": "Confirmed on both vendors' own mobile pages", "items": ["Housecall Pro: offline schedule/job access, in-field payments", "Jobber: clock in/out, quotes, auto-generated invoices", "Neither documents in-field material or job-cost entry in detail", "That entry gap feeds directly into the accuracy of both job-costing screens"]}},

    # ---------- CH11 — not a switch pitch ----------
    {"vo": "Does any of this mean a shop on Jobber should switch to Housecall Pro, or the other way around?", "scene": "chapter", "c": {"num": "11", "title": "Is this a reason to switch platforms?"}},
    {"vo": "No, and it's worth saying plainly. Both platforms do scheduling, dispatch, and invoicing well, and this blog already has a separate, honest comparison of the wider small-shop platform decision. This piece is narrower on purpose: what each one's own job-costing feature tracks, and what its QuickBooks sync actually moves. Switching field platforms carries its own real cost and disruption that this comparison doesn't cover, and shouldn't be the takeaway here.", "scene": "define",
     "c": {"eyebrow": "A narrow comparison, not a verdict", "term": "What this video isn't arguing", "body": "Not \"switch platforms.\" Both do scheduling and invoicing well. This is about job-cost accuracy only."}},

    # ---------- CH12 — what closes the gap ----------
    {"vo": "So if switching platforms isn't the fix, what actually closes this gap for a shop running either one?", "scene": "chapter", "c": {"num": "12", "title": "What actually closes the gap"}},
    {"vo": "A layer that checks the field app's job-costing number against the real QuickBooks general ledger, computing burdened labor cost the same way every time instead of trusting whichever screen happens to be open. That's not a feature toggle inside Jobber or Housecall Pro — it's a reconciliation step that has to sit on top of both systems, comparing what the field app says a job made against what the books actually show for that same period.", "scene": "process",
     "c": {"title": "The reconciliation, walked once a month", "steps": ["Pull the field app's job-costing report for the period", "Pull the matching QuickBooks P&L for the same period", "Compute burdened labor cost the same way, every time", "Flag anything that doesn't match before trusting the margin"]}},
    {"vo": "Four checks any owner can run today, before paying for anything. Check which plan you're actually on against the tier where job costing unlocks, Grow for Jobber, Essentials for Housecall Pro. Pull up the job-costing screen next to your real QuickBooks profit-and-loss for the same month. Confirm your labor rates are current, since neither platform fixes past jobs retroactively. And time how long it takes your office to reconcile the two numbers by hand each month — that's the real cost of this gap, not a missing feature.", "scene": "checklist",
     "c": {"title": "Four checks you can run today", "items": ["Confirm your plan actually includes job costing", "Put the job-costing screen next to your real QuickBooks P&L", "Confirm labor rates are current — no retroactive fixes on either platform", "Time your office's manual reconciliation — that's the real cost"]}},

    # ---------- CH13 — where Top Builder AI fits ----------
    {"vo": "Where does Top Builder AI actually fit, given that no self-serve product connects to Jobber or Housecall Pro today?", "scene": "chapter", "c": {"num": "13", "title": "Where Top Builder AI actually fits"}},
    {"vo": "Through a done-for-you Teardown and Install, not existing software a contractor signs up for and connects alone. It's a human-delivered install that reconciles whichever field platform a shop already runs, Jobber, Housecall Pro, or ServiceTitan, against its actual QuickBooks books, and every dollar it produces comes from deterministic, tested computation, never a guess or an LLM estimate.", "scene": "define",
     "c": {"eyebrow": "Done-for-you, not self-serve", "term": "The Teardown/Install engagement", "body": "Reconciles your real field platform against your real QuickBooks books. Deterministic math. No live self-serve product today."}},
    {"vo": "No shipped self-serve fixer for either platform — this is a sourced method delivered as a configured install against a shop's real data. No invented numbers — every pricing, feature, and sync claim in this video traces to that vendor's own current pricing page or help documentation. No specific integration claimed that isn't verified — this video names what each vendor's own docs say syncs and doesn't, nothing more. And a person approves every number; nothing here auto-edits a shop's books, labor rates, or job records.", "scene": "checklist",
     "c": {"title": "What this is, and isn't", "items": ["No shipped self-serve connector for Jobber or Housecall Pro", "No invented numbers — every claim traces to a vendor's own docs", "No unverified integration claims", "A person approves every number before it's final"]}},

    # ---------- CTA ----------
    {"vo": "So here's the fastest way to check this yourself, tonight. Open your job-costing screen in Jobber or Housecall Pro, whichever one you run, and open your real QuickBooks profit-and-loss for the same month, side by side. If those two profit numbers don't agree, or if you honestly don't know because nobody's ever put them next to each other, that gap is exactly what this video walked through, and exactly what a real reconciliation closes.", "scene": "cta",
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
