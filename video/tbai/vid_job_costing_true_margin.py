"""VALUE VIDEO — True Job Margin: the job-costing system for ServiceTitan contractors (INFORMATIONAL).
Pure value, no pitch. Why the P&L lies about individual jobs, the 5 cost buckets (burden, callbacks,
unbilled change orders), a worked $12K-job example, simple overhead allocation, and the weekly
20-minute job-costing review. CTA = free Job Profit Analyzer.
Renders animated body only. Usage: python vid_job_costing_true_margin.py
"""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)

IMG = str(HERE / "build/img/val2") + "/"
CACHE = HERE / "build/val2_jobcost"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = pathlib.Path("C:/Users/you/Downloads/ServiceTitan Agent platform/assets/video/longform/job-costing-true-margin/body_tbos.mp4")
def P(n): return IMG + n + ".jpg"

B = [
    # ---------- HOOK ----------
    {"vo": "How do you actually know what a job made? Not your average margin for the quarter, this one job, after everything it really cost. Most owners can't say for sure, because a P and L can show a profitable year while individual jobs quietly lose money. So let me show you how to cost a job honestly, labor burden, callbacks, overhead, all of it, plus the weekly twenty-minute rhythm that catches the leaks. It's the exact discipline Top Builder OS runs for you automatically, on every job.", "scene": "hook",
     "c": {"icon": "\U0001F4CA", "title": "What did this job make?", "sub": "How a small trades shop sees the real margin on every job", "pulse": True}},

    # ---------- CH1 — the P&L illusion ----------
    {"vo": "Picture year end. The P and L shows a decent net profit. Cash made it through the winter. By every number your accountant hands you, it was a good year. And hiding inside that good year are jobs that lost money — you just can't see which ones, because the P and L was never built to tell you.", "scene": "photo",
     "c": {"photo": P("pl_night"), "eyebrow": "The P&L illusion", "title": "A profitable year can hide losing jobs", "sub": "The statement averages everything together"}},
    {"vo": "Here's why. Gross margin on a P and L is an average across every job you ran, and averages hide losers. Your best jobs subsidize your worst ones, and the bleeding never shows up as a line item.", "scene": "define",
     "c": {"eyebrow": "Why it lies", "term": "Gross margin is an average", "body": "Your best jobs subsidize your worst ones. The blend looks healthy while individual jobs lose money."}},
    {"vo": "But you don't sell quarters. You sell jobs, one at a time. If you can't see margin per job, you're pricing blind and steering the company by an average. Job costing is simply making the real number visible, job by job.", "scene": "split_photo",
     "c": {"photo": P("jobsite_crew"), "eyebrow": "The unit that matters", "title": "You don't sell quarters. You sell jobs.", "sub": "Margin has to be visible one job at a time"}},

    # ---------- CH2 — the five cost buckets ----------
    {"vo": "So what does a job actually cost? Five buckets. Get all five onto the job and the number is honest. Miss one and the margin is fiction.", "scene": "chapter", "c": {"num": "01", "title": "The five cost buckets"}},
    {"vo": "Labor at its true burdened cost. Materials actually used, including the waste. Equipment and subcontractors. Callbacks and warranty work. And a fair share of overhead. Most contractors track materials and wages well — the other three are where the margin leaks.", "scene": "process",
     "c": {"title": "Every job has five cost buckets", "steps": ["Labor at its burdened cost", "Materials, delivered and used", "Equipment and subcontractors", "Callbacks and warranty work", "A fair share of overhead"]}},

    # ---------- CH3 — labor burden ----------
    {"vo": "Start with the biggest blind spot — what an hour of labor actually costs you.", "scene": "chapter", "c": {"num": "02", "title": "Labor burden"}},
    {"vo": "A tech who earns thirty dollars an hour does not cost you thirty. Payroll taxes, workers comp, insurance, benefits, the truck, the fuel, the phone. For contractors we work with, the true cost typically lands between one point two five and one point four times the wage. That multiplier is your labor burden.", "scene": "stat",
     "c": {"value": "1.25-1.4x", "label": "What a field hour really costs vs. the wage", "source": "Typical range across contractors we work with"}},
    {"vo": "Compute it once a year. Everything you pay to keep a tech on the road, divided by the hours they actually turn wrenches — not the hours on the schedule. That's your loaded rate. Cost every job with it from now on.", "scene": "process",
     "c": {"title": "Find your burden multiplier once", "steps": ["Add employer taxes, comp, and insurance", "Add benefits, truck, fuel, phone, tools", "Divide by actual productive field hours", "That is your loaded hourly rate"]}},

    # ---------- CH4 — the buckets everyone misses ----------
    {"vo": "Now the two buckets almost nobody puts on the job — callbacks, and unbilled change orders.", "scene": "chapter", "c": {"num": "03", "title": "The buckets everyone misses"}},
    {"vo": "A callback is a job with zero revenue and full cost. The truck rolls, the tech burns three hours, parts go in — and none of it lands on the job that caused it. If callbacks don't get costed back to the original job, your worst work looks exactly like your best work.", "scene": "split_photo",
     "c": {"photo": P("callback_van"), "eyebrow": "Bucket four", "title": "A callback is revenue zero, cost full", "sub": "Cost it back to the job that caused it"}},
    {"vo": "And unbilled change orders — the scope grew, the price didn't. The extra visit nobody invoiced. The upgrade thrown in to keep the customer happy. Real cost, no revenue attached, and it quietly rewrites the margin on the job.", "scene": "checklist",
     "c": {"title": "Unbilled change orders look like", "items": ["The extra visit nobody invoiced", "Scope that grew as a favor", "Materials upgraded mid job", "Hours past the estimate, absorbed"]}},

    # ---------- CH5 — the worked example ----------
    {"vo": "Let me make this concrete with one job — the kind of pattern we see over and over when contractors cost their jobs honestly for the first time.", "scene": "chapter", "c": {"num": "04", "title": "The $12,000 job"}},
    {"vo": "A twelve thousand dollar job. Materials came to about forty six fifty. Payroll wages for the hours on it, about twenty five seventy six. Most owners do that math in their head — twelve minus seven — and call it a forty percent job. Feels like a winner.", "scene": "photo",
     "c": {"photo": P("worked_job"), "eyebrow": "The gut math", "title": "On gut math it looks like 40%", "sub": "$12,000 revenue, $4,650 materials, $2,576 wages"}},
    {"vo": "Now cost it honestly. Burden the labor at one point three five — nine hundred and two dollars the paystubs never showed. Three days of trencher rental, five forty. The callback three weeks later, four ten with parts. True gross profit: twenty nine twenty two — twenty four percent, not forty. And we're not done.", "scene": "process",
     "c": {"title": "Now cost it honestly", "steps": ["Labor burden at 1.35x adds $902", "Three equipment days add $540", "One callback visit adds $410", "True gross profit: $2,922, about 24%"]}},
    {"vo": "Because the job also carries its share of the office. At twenty percent overhead — about typical for contractors we work with — that's twenty four hundred dollars. What's left is five hundred and twenty two. A four percent job wearing a forty percent costume.", "scene": "stat",
     "c": {"value": "4%", "label": "What the $12,000 job truly kept after overhead"}},
    {"vo": "Nobody did anything wrong on that job. The costs were just invisible — spread across payroll runs, insurance bills, and a callback that landed in a different month. Job costing makes them visible in one place, per job.", "scene": "split_photo",
     "c": {"photo": P("dashboard_margin"), "eyebrow": "The lesson", "title": "The costs were invisible, not absent", "sub": "Job costing puts them in one place, per job"}},

    # ---------- CH6 — overhead allocation ----------
    {"vo": "About that overhead share. Contractors overcomplicate this step, get frustrated, and quit. Here's the simple version that actually gets used.", "scene": "chapter", "c": {"num": "05", "title": "Allocating overhead simply"}},
    {"vo": "Add up a year of overhead — rent, office payroll, software, insurance, marketing. Divide by the year's revenue. That's your rate. Eighteen percent means every job carries eighteen percent of its revenue. Prefer hours? Divide by field hours instead. Either works — pick one and stay consistent, because a simple rate you use beats a perfect one you don't.", "scene": "process",
     "c": {"title": "The simple overhead method", "steps": ["Add up last year's overhead spend", "Divide by last year's revenue", "That percent rides on every job", "Or divide by field hours instead", "Review the rate twice a year"]}},

    # ---------- CH7 — the weekly rhythm ----------
    {"vo": "Now the rhythm that makes all of this stick. Not a quarterly project. Not a cleanup for the accountant. Twenty minutes, once a week.", "scene": "chapter", "c": {"num": "06", "title": "The weekly 20-minute review"}},
    {"vo": "Same day every week — Friday morning works. Coffee, one screen, last week's closed jobs. In Top Builder OS the timesheets and purchase orders are already attached to each job, so you're not hunting for data. You're reviewing it.", "scene": "photo",
     "c": {"photo": P("office_manager"), "eyebrow": "The rhythm", "title": "Twenty minutes, every Friday", "sub": "Last week's closed jobs, one screen"}},
    {"vo": "Five steps. Pull the closed jobs. Load burdened labor, materials, and equipment against each one. Post callbacks to the job that caused them. Take out overhead. Then flag anything under target — and ask why while people still remember the job.", "scene": "process",
     "c": {"title": "The 20-minute job review", "steps": ["Pull last week's closed jobs", "Load burdened labor, materials, equipment", "Post callbacks to the job that caused them", "Subtract each job's overhead share", "Flag anything under your target"]}},
    {"vo": "Every flagged job is one of three problems. The estimate was wrong — fix the template. Execution slipped — hours, waste, rework. Or the price is too low for what the work costs. Different problem, different fix — and you only get to choose the fix if you can see the number.", "scene": "checklist",
     "c": {"title": "A flagged job is one of three problems", "items": ["The estimate was wrong. Fix the template.", "Execution slipped. Hours, waste, rework.", "The price is too low. Raise it or walk."]}},

    # ---------- CH8 — chronically thin job types ----------
    {"vo": "And when the weekly review keeps flagging the same type of job? That's not a bad week anymore. That's a pattern. And a pattern gets one of four moves.", "scene": "chapter", "c": {"num": "07", "title": "When a job type runs chronically thin"}},
    {"vo": "Reprice it — the old price was set against fiction. Re-scope what's included by default. Retrain the crew that runs long — that's coaching, not pricing. Or retire it. Some work isn't worth winning, and honest numbers give you the confidence to walk away.", "scene": "checklist",
     "c": {"title": "Four moves for a thin job type", "items": ["Reprice it against the true cost", "Re-scope what is included by default", "Retrain the crew that runs long", "Retire it and sell the profitable work"]}},

    # ---------- CH9 — the free analyzer ----------
    {"vo": "This is exactly what Top Builder OS does on every job, automatically. Every hour posts at its true burdened cost, every material lands on the job, callbacks get costed back, and overhead is allocated — so the real margin on each job is there the moment it closes, not three weeks later in a spreadsheet.", "scene": "photo",
     "c": {"photo": P("analyzer_mockup"), "eyebrow": "One system", "title": "Top Builder OS costs every job", "sub": "True margin per job, the moment it closes"}},
    {"vo": "Take the biggest job you closed last month, and picture knowing its real margin the day it closed instead of guessing months later. That is what running the whole shop on one system gets you. See it at topbuilderai.com.", "scene": "cta",
     "c": {"eyebrow": "From Top Builder OS", "title": "Know What Every Job Made", "sub": "One system for the jobs and the books", "url": "topbuilderai.com"}},
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
