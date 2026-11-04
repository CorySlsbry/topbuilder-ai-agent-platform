"""VALUE VIDEO — Does ServiceTitan track job cost in real time? (INFORMATIONAL, sourced).
Companion long-form to landing/blog/servicetitan-real-time-job-cost-tracking.html (which already
has its companion short, youtu.be/P76NlRJtBB4). Same sourced facts: ServiceTitan's own docs describe
a genuine real-time Budget vs Actual table, gated behind Project Management + a support ticket +
paperwork lag; the WIP report is a manual snapshot, not a dashboard; no proactive overrun alert
exists; the "fewer overruns" stats trace to no named study; committed-vs-actual cost is the blind
spot that hides mid-job drift. Adapted from vid_job_costing_true_margin.py's proven shape — image-
free scenes throughout (hook/chapter/define/stat/process/checklist/cta), no missing-asset risk.
Renders animated body only. Usage: python vid_realtime_job_cost_tracking.py
"""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)

CACHE = HERE / "build/val_realtime"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = pathlib.Path("C:/Users/you/Downloads/ServiceTitan Agent platform/assets/video/longform/realtime-job-cost-tracking/body.mp4")

B = [
    # ---------- HOOK ----------
    {"vo": "How do you actually know a ServiceTitan job is losing money while the crew is still on site, not three weeks later once the invoice finally posts. Most shops can't answer that in real time, and it's not because nobody's watching. It's because the tool most residential and light-commercial ServiceTitan accounts use for job costing was built to lock in a number after the fact, not to watch one while it's still moving. So let's go through exactly what ServiceTitan's own documentation says is real time, what it actually takes to turn on, the gap left even when it is on, and how a shop catches a job drifting over budget while there's still time to do something about it.", "scene": "hook",
     "c": {"icon": "⏱️", "title": "Is this job losing money — right now?", "sub": "What ServiceTitan's own docs say about mid-job visibility", "pulse": True}},

    # ---------- CH1 — does it exist ----------
    {"vo": "First question: does ServiceTitan have anything that tracks cost in real time while a job is still open?", "scene": "chapter", "c": {"num": "01", "title": "Does it track cost in real time?"}},
    {"vo": "Yes, and it's real, not a marketing exaggeration. ServiceTitan's own help documentation for a feature called Budget vs Actual states plainly that the table updates in real time as you work through a project and generate actuals, showing percent of budget used, variance, balance to finish, and a forecasted cost at completion.", "scene": "define",
     "c": {"eyebrow": "It's a real feature", "term": "Budget vs Actual", "body": "Updates in real time: percent of budget used, variance, balance to finish, forecasted cost at completion."}},
    {"vo": "The catch is scope. That same documentation says Budget vs Actual only exists inside Project Management, a separate feature set built for ServiceTitan's commercial and construction side. A shop running ordinary residential or light-commercial Jobs, which is most of the install base, doesn't see this table anywhere in their account. What they see instead is the standard Job Costing flyout, built from the invoice, and it locks the moment that invoice posts and exports.", "scene": "checklist",
     "c": {"title": "Where the real-time table actually lives", "items": ["Real-time Budget vs Actual — inside Project Management only", "Most residential / light-commercial accounts don't have it", "Standard Job Costing flyout instead, locks at invoice", "Real-time tracking exists. Most contractors aren't looking at it"]}},

    # ---------- CH2 — turning it on ----------
    {"vo": "So say a shop wants it. What does it actually take to turn Budget vs Actual on?", "scene": "chapter", "c": {"num": "02", "title": "What it takes to turn it on"}},
    {"vo": "More than a settings toggle. ServiceTitan's own documentation for project financials says account configuration is required, and tells you to contact Technical Support for details, and separately that Budget vs Actual has to already be enabled before the visual project financials view will even show. Once it's configured, the underlying numbers are straightforward: Contract Value is the price and tax of every sold estimate, Actual Billed is invoiced income minus retainage, and Total Budgeted Expense is the sum of estimated costs.", "scene": "process",
     "c": {"title": "Turning it on, per ServiceTitan's own docs", "steps": ["A support ticket, not a checkbox", "Contract Value = price + tax of sold estimates", "Actual Billed = invoiced income minus retainage", "Total Budgeted Expense = sum of estimated costs"]}},

    # ---------- CH3 — what real time means ----------
    {"vo": "Here's the part worth slowing down on: what does real time actually mean if the numbers only post once someone bills or gets billed?", "scene": "chapter", "c": {"num": "03", "title": "What \"real time\" actually means"}},
    {"vo": "It means the table refreshes instantly. It does not mean the inputs arrive instantly. ServiceTitan's own documentation says actuals start calculating only when you generate an invoice, receive a bill, or issue a return, and that technician labor is calculated at the hourly rate times paid hours worked, not clocked hours. A tech's time on a job today doesn't become an actual labor cost until payroll actually runs and pays it.", "scene": "define",
     "c": {"eyebrow": "Real time about entry, not the work", "term": "Actuals only post on paperwork", "body": "Invoice, bill, or paid timesheet — not the moment a tech clocks in or a truck rolls."}},
    {"vo": "That pattern repeats across every real-time claim ServiceTitan documents. The table itself is real. What feeds it is gated, behind a module most accounts don't have, a support ticket to turn it on, or paperwork that hasn't cleared yet. None of that is dishonest. It's just not the same thing as watching a job while it's still moving.", "scene": "checklist",
     "c": {"title": "Every real-time claim, once you check the docs", "items": ["Real, but gated behind Project Management", "Real, but gated behind a support-configured setup", "Real, but gated behind an invoice, bill, or paid timesheet", "Real time about entry — not real time about the work"]}},

    # ---------- CH4 — WIP report ----------
    {"vo": "What about the Work in Progress report — is that a live dashboard you can check anytime?", "scene": "chapter", "c": {"num": "04", "title": "The WIP report isn't a live dashboard"}},
    {"vo": "No. ServiceTitan's own documentation for the WIP report describes a report you manually run: go to Reports, click All Reports, click WIP, set a Project start date and an As of date, then click Run Report. That's a point-in-time export built around percentage-of-completion accounting for month-end revenue recognition, not a dashboard sitting open that refreshes as the crew works.", "scene": "process",
     "c": {"title": "Generating the WIP report", "steps": ["Reports → All Reports → WIP", "Set a Project start date", "Set an \"As of\" date", "Click Run Report — a snapshot, not a feed"]}},

    # ---------- CH5 — no alert ----------
    {"vo": "Does ServiceTitan at least alert you automatically when a job is trending over budget?", "scene": "chapter", "c": {"num": "05", "title": "No alert fires when a job drifts"}},
    {"vo": "Nothing in ServiceTitan's own documentation describes a proactive alert. The Project Management feature page promises real-time visibility to keep a project on budget, and a Project Portfolio view billed as flagging which projects require attention. But that's a description of a screen, not an event — no notification, email, or push alert fires when a job crosses a budget threshold. Someone still has to open the table and look, on every job, every day.", "scene": "define",
     "c": {"eyebrow": "Nobody gets pinged", "term": "\"Requires attention\" is a screen, not an alert", "body": "Color-coded columns you check yourself — no notification when a job crosses its budget."}},

    # ---------- CH6 — unverified stats ----------
    {"vo": "ServiceTitan's own marketing cites numbers on this. Are they backed by a named study?", "scene": "chapter", "c": {"num": "06", "title": "Are the \"fewer overruns\" numbers verified?"}},
    {"vo": "No, and it's worth stating plainly. ServiceTitan's own blog post on real-time job costing states contractors using integrated job costing report twenty five percent fewer budget overruns, and that projects with committed cost tracking see fifteen percent fewer overruns. Neither figure traces to a named study, an outside survey, or a dated source anywhere in that post. Treat both as ServiceTitan's own marketing claims about its own product category, not independently verified results.", "scene": "stat",
     "c": {"value": "25% / 15%", "label": "ServiceTitan's own \"fewer overruns\" claims — no named study behind either number", "source": "ServiceTitan's own blog post on real-time job costing"}},

    # ---------- CH7 — committed vs actual ----------
    {"vo": "Now the gap that matters most while a job is still open: committed cost versus actual cost.", "scene": "chapter", "c": {"num": "07", "title": "Committed cost vs. actual cost"}},
    {"vo": "Committed cost is money already tied up in a purchase order a vendor hasn't billed yet. Actual cost is money already billed. A job can look perfectly on-budget mid-project purely because real, already-incurred expense is sitting as committed instead of actual, and Budget vs Actual only counts a cost once the bill lands. Watching actual cost alone misses spend that already happened in the field but hasn't been invoiced yet.", "scene": "define",
     "c": {"eyebrow": "The blind spot inside the blind spot", "term": "Committed cost vs. actual cost", "body": "A purchase order the vendor hasn't billed yet is real spend — and it's invisible until the bill lands."}},

    # ---------- CH8 — why it hits materials/fixed-price ----------
    {"vo": "Why does this matter more on materials-heavy or fixed-price jobs specifically?", "scene": "chapter", "c": {"num": "08", "title": "Why materials-heavy and fixed-price jobs feel this most"}},
    {"vo": "Because the two most common ways a job goes over budget both happen mid-project, not at closeout. A materials substitution or price change burns through the budgeted allowance faster than planned. Or a fixed-price job runs longer than estimated and keeps billing labor hours against a contract value that never moves. Both are fixable while the crew still has work left to do — swap a supplier, write a change order, have the scope conversation. Neither is fixable once the invoice has already posted.", "scene": "checklist",
     "c": {"title": "Two ways a job drifts mid-project", "items": ["A materials substitution burns the allowance early", "A fixed-price job runs long against a fixed contract", "Both fixable — while the crew is still on site", "Neither fixable once the invoice has already posted"]}},

    # ---------- CH9 — third-party tools ----------
    {"vo": "Is this a ServiceTitan-specific gap, or does the wider industry build around it too?", "scene": "chapter", "c": {"num": "09", "title": "Third-party tools built for this exact gap"}},
    {"vo": "Third-party job-costing tools exist specifically because this gap is real, and their own marketing proves it. Knowify's own site says most contractors find out a job lost money after it's done, and shows where a job stands before it's too late to act. Buildertrend's help documentation describes a real-time view of estimated cost, actual spend, and profitability by cost code. Dapt's HVAC job-costing page promises real-time visibility into labor, equipment, and material cost to prevent overruns. None of the three plug natively into ServiceTitan.", "scene": "checklist",
     "c": {"title": "Tools built around this exact gap", "items": ["Knowify — cost visibility before it's too late to act", "Buildertrend — real-time cost by cost code", "Dapt — labor, equipment, material visibility for HVAC", "None plug natively into ServiceTitan"]}},

    # ---------- CH10 — worked example ----------
    {"vo": "Let's make this concrete with one job. This example is illustrative, built to show the mechanism, not a client result.", "scene": "chapter", "c": {"num": "10", "title": "One job, worked through"}},
    {"vo": "An eighteen thousand five hundred dollar fixed-price bathroom remodel, sixty percent through its schedule, has already used seventy eight percent of its material budget after a supply substitution, and two change-order hours are logged but not yet billed. Nothing forces anyone to compare sixty percent done against seventy eight percent spent. Nothing in the standard flyout, nothing in Budget vs Actual, nothing in the WIP report, surfaces that gap on its own. Whoever finds out, finds out whenever the invoice finally posts, weeks later.", "scene": "stat",
     "c": {"value": "60% vs. 78%", "label": "Schedule complete vs. material budget already spent — one illustrative $18,500 remodel", "source": "Illustrative walkthrough, not a client result"}},

    # ---------- CH11 — how Top Builder AI catches it ----------
    {"vo": "So how does a shop actually catch this while the job is still open?", "scene": "chapter", "c": {"num": "11", "title": "Catching drift while the job is still open"}},
    {"vo": "The Financial and Pricebook agents inside Top Builder AI pull ServiceTitan's committed costs, actual costs, and paid-hours labor data continuously, instead of waiting on an invoice or a manually run report. They read committed and actual cost side by side. They compare schedule progress against spend, the exact comparison nothing in ServiceTitan does automatically. They recompute labor at its burdened cost as it's logged, without waiting on payroll to run. And when drift crosses a set tolerance, the job gets flagged for review while there's still time to swap a supplier, write a change order, or have the scope conversation.", "scene": "process",
     "c": {"title": "How the drift gets caught early", "steps": ["Read committed and actual cost together", "Compare schedule progress against spend", "Recompute burdened labor as it's logged", "Flag drift past tolerance while the job's open", "A human decides — nothing gets edited automatically"]}},

    # ---------- CH12 — does it replace ServiceTitan ----------
    {"vo": "Last question — does any of this replace ServiceTitan's Projects module or its Budget vs Actual table?", "scene": "chapter", "c": {"num": "12", "title": "Does this replace ServiceTitan?"}},
    {"vo": "No. ServiceTitan stays the system of record for the job, the budget, and the invoice. Where Project Management is turned on and configured, Budget vs Actual keeps working exactly as it does today. The agents read the same committed and actual cost data ServiceTitan already tracks, whether or not that module is enabled, and surface a projected margin while the job is still open — closer to the always-current view ServiceTitan's own marketing describes than what a standard account without Project Management delivers on its own.", "scene": "define",
     "c": {"eyebrow": "What doesn't change", "term": "ServiceTitan stays the system of record", "body": "Same data ServiceTitan already tracks — surfaced while the job's still open, with or without Project Management turned on."}},
    {"vo": "No edited records — your ServiceTitan data stays exactly as your team enters it. No invented numbers — committed cost, actual cost, and schedule progress come from your real data, never a guess presented as fact. No blind self-serve signup — it's configured against your actual ServiceTitan and payroll data. And it works whether or not Project Management is turned on for your account.", "scene": "checklist",
     "c": {"title": "What this is, and isn't", "items": ["No edited records — your ServiceTitan data stays as entered", "No invented numbers — real committed and actual cost only", "Not a blind self-serve signup — configured on your real data", "Works whether or not Project Management is turned on"]}},

    # ---------- CTA ----------
    {"vo": "So here's the fastest way to check this yourself. Open a job that's still in progress right now and see whether a Budget vs Actual table even appears. If it doesn't, there's no real-time cost table on that account today, only the standard flyout that locks at invoice. If it does, check how many committed costs on that job haven't moved to actual yet — that gap is exactly what a mid-project overrun hides inside.", "scene": "cta",
     "c": {"eyebrow": "Find out before the invoice tells you", "title": "Is Your Shop Watching the Right Number?", "sub": "Check whether Budget vs Actual is even turned on", "url": "topbuilderai.com"}},
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
