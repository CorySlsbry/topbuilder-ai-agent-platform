"""VALUE VIDEO — How We Automate a Contractor's Entire Back Office (INFORMATIONAL).
Pure value, no pitch. Full walkthrough of ServiceTitan back-office automation —
pricebook, job costing, A/R, dispatch, payroll. CTA = free ServiceTitan Automation Calculator.
Renders animated body only. Usage: python vid_back_office_automation.py
"""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)

IMG = str(HERE / "build/img/val") + "/"
CACHE = HERE / "build/val_backoffice"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = pathlib.Path("C:/Users/you/Downloads/ServiceTitan Agent platform/assets/video/longform/contractor-back-office-auto/body.mp4")
def P(n): return IMG + n + ".jpg"

B = [
    # ---------- HOOK ----------
    {"vo": "I'm going to walk you through exactly how we automate a contractor's entire back office using ServiceTitan — pricebook, job costing, collections, dispatch, payroll — all of it. And I built a free calculator so you can see exactly how much time and money automation would save your specific company.", "scene": "hook",
     "c": {"title": "How We Automate a Contractor's\nEntire Back Office", "sub": "Pricebook · Job costing · Collections · Dispatch · Payroll", "pulse": True}},

    # ---------- CH1 — the back office trap ----------
    {"vo": "Let me describe a week that probably sounds familiar. Monday morning, your office manager is reconciling last week's invoices. Tuesday she's chasing three customers who haven't paid. Wednesday it's a pricebook update because your supplier changed prices again. Thursday, payroll prep. Friday, she's too buried to answer the phone.", "scene": "photo",
     "c": {"photo": P("buried_desk"), "title": "Sound familiar?", "sub": "Invoices · Collections · Pricebook · Payroll · Too buried to answer the phone"}},
    {"vo": "The back office is where contractors bleed money without realizing it. Not from one big mistake — from a thousand small inefficiencies that add up to fifteen, twenty hours a week of manual work that software could handle.", "scene": "stat",
     "c": {"value": "15-20 hrs", "label": "Weekly hours lost to manual back-office work", "source": "Top Builder AI client average"}},
    {"vo": "ServiceTitan is a powerful platform, but most contractors use maybe thirty percent of what it can do. The rest is sitting there, unused, while their team does the work by hand. That's what we fix.", "scene": "stat",
     "c": {"value": "30%", "label": "Average ServiceTitan feature utilization"}},

    # ---------- CH2 — the automation stack overview ----------
    {"vo": "Here's the full automation stack we build. Six systems, each one independent, each one saving real hours the first week it runs.", "scene": "chapter", "c": {"num": "01", "title": "The automation stack"}},
    {"vo": "Pricebook sync. Job costing automation. A-R collections. Dispatch optimization. Estimate follow-up. And payroll prep. I'm going to walk you through each one — what it does, how it works in ServiceTitan, and what it saves.", "scene": "cards",
     "c": {"title": "Six systems, six wins", "items": [("\U0001F4B0", "Pricebook sync"), ("\U0001F4CB", "Job costing"), ("\U0001F4B3", "A/R collections"), ("\U0001F69A", "Dispatch"), ("\U0001F4DD", "Estimate follow-up"), ("\U0001F4B5", "Payroll prep")]}},

    # ---------- CH3 — Pricebook sync ----------
    {"vo": "System one — pricebook sync. This is the foundation because everything in ServiceTitan flows from your pricebook. If your prices are stale, your estimates are wrong, your margins erode, and you don't find out until the end of the quarter.", "scene": "chapter", "c": {"num": "02", "title": "Pricebook sync"}},
    {"vo": "What we build pulls supplier price updates automatically, compares them against your current pricebook, flags anything where your margin dropped below your threshold, and generates the update — ready for a one-click approval. Your office manager goes from spending four hours a week on this to four minutes.", "scene": "process",
     "c": {"title": "How pricebook sync works", "steps": ["Pull supplier price updates", "Compare against current pricebook", "Flag items below margin threshold", "Generate update for one-click approval"]}},
    {"vo": "The margin protection alone pays for itself. We've seen contractors discover they were selling materials at cost on fifteen to twenty line items because nobody caught the supplier increase. That's thousands of dollars a month just leaking out.", "scene": "stat",
     "c": {"value": "$2-5K/mo", "label": "Typical margin leakage from stale pricebooks"}},

    # ---------- CH4 — Job costing ----------
    {"vo": "System two — automated job costing. This is the one that changes how you think about your business.", "scene": "chapter", "c": {"num": "03", "title": "Job costing automation"}},
    {"vo": "After every job closes, the automation pulls the actual labor hours from ServiceTitan timesheets, the actual materials from the purchase orders, calculates the true cost, and compares it against what you estimated. If a job came in under margin, you know the same day — not sixty days later when the accountant catches it.", "scene": "process",
     "c": {"title": "Automated job costing flow", "steps": ["Pull actual labor hours from timesheets", "Pull actual materials from POs", "Calculate true job cost", "Compare vs. estimate", "Flag under-margin jobs same day"]}},
    {"vo": "The real power is the pattern recognition. After a few months, the system can tell you which job types consistently lose money, which techs are faster on which work, and where your estimates need adjusting. Data-driven decisions instead of gut feel.", "scene": "checklist",
     "c": {"title": "What the data reveals", "items": ["Which job types consistently lose money", "Which techs are fastest on which work", "Where estimates need adjusting", "Seasonal cost pattern shifts", "Material waste by category"]}},

    # ---------- CH5 — A/R Collections ----------
    {"vo": "System three — A-R collections. This is the one that improves your cash flow overnight.", "scene": "chapter", "c": {"num": "04", "title": "A/R collections"}},
    {"vo": "Most contractors have tens of thousands sitting in unpaid invoices right now because nobody has time to chase them. The automation runs a sequence — email at seven days, text at fourteen, phone call at twenty-one, and escalation at thirty. Every invoice, every time, no exceptions.", "scene": "process",
     "c": {"title": "The collections sequence", "steps": ["Day 7: automated email reminder", "Day 14: friendly text message", "Day 21: phone call (AI or staff)", "Day 30: escalation notice"]}},
    {"vo": "We typically cut days-to-collect by forty to fifty percent in the first ninety days. For a company doing fifty thousand a month, that can free up twenty to thirty thousand in cash that was just sitting in receivables.", "scene": "stat",
     "c": {"value": "40-50%", "label": "Reduction in days-to-collect within 90 days"}},

    # ---------- CH6 — Dispatch + Estimate follow-up ----------
    {"vo": "Systems four and five — dispatch optimization and estimate follow-up. I'll cover both because they share the same principle: stop leaving money on the table.", "scene": "chapter", "c": {"num": "05", "title": "Dispatch & estimates"}},
    {"vo": "Dispatch optimization looks at tech skills, location, drive time, and current capacity to route the right tech to the right job. Less windshield time, more billable hours, better first-time fix rates.", "scene": "compare",
     "c": {"title": "Smart dispatch vs. manual", "cols": ["AI Dispatch", "Manual"],
           "rows": [("Skill-matched routing", [True, False]), ("Drive-time minimized", [True, False]),
                    ("Capacity balanced", [True, False]), ("Real-time rerouting", [True, False]),
                    ("Handles exceptions well", [False, True])]}},
    {"vo": "Estimate follow-up is pure found money. Every unsigned estimate sitting in ServiceTitan is revenue waiting to happen. The automation sends a personalized follow-up at three days, seven days, and fourteen days — and we've seen close rates jump by twenty to thirty percent just from consistent follow-up.", "scene": "stat",
     "c": {"value": "+20-30%", "label": "Estimate close rate increase from automated follow-up"}},

    # ---------- CH7 — Payroll prep ----------
    {"vo": "System six — payroll prep. The one your office manager will thank you for.", "scene": "chapter", "c": {"num": "06", "title": "Payroll prep"}},
    {"vo": "The automation pulls timesheet data from ServiceTitan, reconciles it against job records, flags any discrepancies — a tech who clocked eight hours but only has six hours of job time, overtime thresholds, missing entries — and generates a clean payroll-ready report. What used to take half a day now takes ten minutes of review.", "scene": "process",
     "c": {"title": "Payroll automation flow", "steps": ["Pull timesheet data from ServiceTitan", "Reconcile against job records", "Flag discrepancies and overtime", "Generate payroll-ready report"]}},

    # ---------- CH8 — Implementation reality ----------
    {"vo": "Now let me be honest about implementation, because I think you deserve the real version, not the sales version.", "scene": "chapter", "c": {"num": "07", "title": "Implementation reality"}},
    {"vo": "You don't automate everything at once. We start with the highest-ROI system — usually collections or pricebook — get it running smoothly, prove the win, then layer on the next one. Ninety days to get the core three running. Six months for the full stack.", "scene": "process",
     "c": {"title": "The 90-day build", "steps": ["Days 1-30: First system live (highest ROI)", "Days 31-60: Second system + tune first", "Days 61-90: Third system + full integration", "Months 4-6: Remaining systems layered in"]}},
    {"vo": "The total time your team invests is about two hours in the first week for setup questions, then fifteen minutes a week reviewing reports and approving changes. That's it. We handle the build, the monitoring, and the tuning.", "scene": "stat",
     "c": {"value": "15 min/wk", "label": "Your team's ongoing time investment"}},

    # ---------- CH9 — Your free calculator ----------
    {"vo": "I built a free calculator specifically for contractors. You plug in your team size, your ticket volume, and how many hours your office spends on each of these tasks — and it shows you exactly which systems to automate first, how much you'd save, and a ninety-day implementation timeline.", "scene": "photo",
     "c": {"photo": P("calculator_mockup"), "title": "ServiceTitan Automation Calculator", "sub": "Free · Personalized ROI · 90-day roadmap"}},
    {"vo": "It takes about two minutes, and you'll walk away knowing the exact dollar value of automating your back office. Link's in the description — go run your numbers.", "scene": "cta",
     "c": {"eyebrow": "Free from Top Builder AI", "title": "Calculate Your Automation ROI", "sub": "Your numbers, your savings, your roadmap", "url": "topbuilderai.com/calculator"}},
]

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    secs = ae.render_body(B, OUT, CACHE)
    print(f"BODY {secs:.1f}s ({secs/60:.1f} min), {len(B)} beats -> {OUT}")
