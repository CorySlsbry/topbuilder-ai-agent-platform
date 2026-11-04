"""VALUE VIDEO — Best AI Tools for HVAC, Plumbing & Electrical Contractors (2026) (INFORMATIONAL).
Companion to landing/blog/best-ai-tools-hvac-plumbing-electrical-contractors-2026.html. TJ
question-ladder: what's on the lists, what ServiceTitan's own AI does, what AI receptionists do,
Bluon field diagnostics, the full 3-layer landscape compare, what's missing (the back office), the
74%-see-it-25%-use-it adoption gap, and where Top Builder AI fits. No pricing for any tool, ours or
a competitor's — every figure here is a usage/adoption stat, not a price.
Renders animated body only. Usage: python vid_best_ai_tools_2026.py
"""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)

CACHE = HERE / "build/best_ai_tools_2026"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = pathlib.Path("C:/Users/you/Downloads/ServiceTitan Agent platform/assets/video/longform/best-ai-tools-2026/body.mp4")

B = [
    # ---------- HOOK ----------
    {"vo": "What's actually the best AI tool for an HVAC, plumbing, or electrical shop in 2026? Every list you've seen answers a piece of it, and none of them answer all of it. I read the two roundups everybody's citing, checked what ServiceTitan's own AI does, what the AI receptionists do, what the field-diagnostics tool does, and I found the one row every single list is missing. Let's go through the whole landscape.", "scene": "hook",
     "c": {"icon": "\U0001F916", "title": "Best AI Tools for Contractors, 2026", "sub": "What's actually on the lists, and what every list is missing", "pulse": True}},

    # ---------- CH1 — what's on the lists ----------
    {"vo": "First, what actually shows up when someone searches 'best AI tools for contractors.'", "scene": "chapter", "c": {"num": "01", "title": "What's actually on the lists"}},
    {"vo": "I read two of the roundups getting cited right now. One AI-receptionist comparison covering five tools, two field-guide roundups covering twelve to thirteen tools each for plumbing and electrical. Seventeen tools total, checked across both. Zero of them touch the back office.", "scene": "stat",
     "c": {"value": "17 tools, 0 back office", "label": "Two independent 2026 roundups — front-office, booking, and field-diagnostic AI only", "source": "PipelineOn AI-receptionist comparison + BuildOps plumbing/electrical AI-tools guides, 2026"}},
    {"vo": "Almost everything on those lists is a front-office tool — it answers the phone, texts a lead back, or gets a visit on the calendar. That's one job in the shop. It's an important one. It is not the whole business.", "scene": "define",
     "c": {"eyebrow": "The pattern", "term": "Nearly every tool on every list is front-office", "body": "Answering the phone and booking the calendar. One job in the shop — not the whole business."}},

    # ---------- CH2 — ServiceTitan's own AI ----------
    {"vo": "Second question — what does ServiceTitan's own AI, Titan Intelligence, actually do?", "scene": "chapter", "c": {"num": "02", "title": "ServiceTitan's own AI"}},
    {"vo": "Titan Intelligence lives inside ServiceTitan and reads ServiceTitan data — call summaries, dispatch suggestions, a KPI view built from your ServiceTitan modules. It's genuinely useful, and it's also scoped to one system. It has no idea what your QuickBooks says.", "scene": "define",
     "c": {"eyebrow": "What it is", "term": "Titan Intelligence reads ServiceTitan, and only ServiceTitan", "body": "Call summaries, dispatch suggestions, KPIs built from your ST modules. QuickBooks is invisible to it."}},

    # ---------- CH3 — AI receptionists ----------
    {"vo": "Third — the category everyone means when they say 'AI for contractors': the AI receptionists.", "scene": "chapter", "c": {"num": "03", "title": "The AI receptionists"}},
    {"vo": "Four names come up over and over. Jobber's built-in AI Receptionist. Podium, webchat plus missed-call text-back. Avoca, a voice agent for the phones. Sameday AI, always-on booking. Different vendors, same job.", "scene": "cards",
     "c": {"title": "The names on every front-office list", "items": [
         ("\U0001F4DE", "Jobber AI Receptionist — books straight into Jobber"),
         ("\U0001F4AC", "Podium — webchat + missed-call text-back"),
         ("\U0001F5E3️", "Avoca — AI voice agent for the phones"),
         ("⚡", "Sameday AI — always-on booking assistant")]}},
    {"vo": "All four solve the same problem — get the phone answered and the job on the calendar, especially after hours. None of them touch what happens after the job is booked. That's not a knock — it's just not what they were built for.", "scene": "define",
     "c": {"eyebrow": "What they solve, and stop at", "term": "They get the lead captured and the visit scheduled", "body": "Then their job is done. Pricing, dispatch, job cost, collections — outside their scope entirely."}},

    # ---------- CH4 — field diagnostics ----------
    {"vo": "Fourth — is there an AI tool built specifically for field diagnostics? Yes, and it's the one category on these lists that isn't front-office.", "scene": "chapter", "c": {"num": "04", "title": "Field diagnostics"}},
    {"vo": "Bluon is an AI diagnostic app — a tech describes symptoms in plain language on-site and gets troubleshooting guidance back. It's reportedly used by over a hundred and seventy thousand technicians. Genuinely different animal: it helps diagnose the unit, not run the office.", "scene": "stat",
     "c": {"value": "170,000+", "label": "Technicians reportedly using Bluon for AI-assisted field diagnostics", "source": "Bluon, as cited across 2026 field-diagnostics roundups"}},

    # ---------- CH5 — the full landscape ----------
    {"vo": "Put all three categories side by side and the pattern is obvious.", "scene": "chapter", "c": {"num": "05", "title": "The full 2026 landscape"}},
    {"vo": "AI receptionists answer and book. Bluon helps a tech diagnose in the field. Neither one touches the pricebook, the AR aging list, a dispatch call weighed against margin, or what a job actually cost when it closed.", "scene": "compare",
     "c": {"title": "Three layers, one of them missing everywhere", "cols": ["AI Receptionist", "Field Diagnostics", "Top Builder AI"],
       "rows": [("Answers calls, books the visit", [True, False, False]),
                ("Helps a tech diagnose on-site", [False, True, False]),
                ("Keeps the vendor pricebook current", [False, False, True]),
                ("Prioritizes the AR chase list", [False, False, True]),
                ("Weighs margin, not just drive time, on dispatch", [False, False, True]),
                ("Reads both ServiceTitan and QuickBooks", [False, False, True])]}},

    # ---------- CH6 — what's missing ----------
    {"vo": "Sixth — what is missing from every list published so far? The back office. Not one of the seventeen tools checked for this touches the accounts-receivable queue, keeps a vendor pricebook current, weighs overtime and margin on a dispatch decision, tracks job-level cost, or pulls a weekly KPI scorecard out of both ServiceTitan and QuickBooks.", "scene": "chapter", "c": {"num": "06", "title": "What every list is missing"}},
    {"vo": "Five things, checked against all seventeen tools, present on none of them.", "scene": "checklist",
     "c": {"title": "Not on a single list", "items": [
         "Vendor pricebook freshness",
         "AR collections priority",
         "Dispatch margin, not just drive time",
         "True cost per job",
         "A weekly KPI scorecard from both systems"]}},
    {"vo": "Every list on the market answers 'how do I capture more leads.' None of them answer 'how do I run the numbers on the jobs I already booked.' That second question is the one that decides whether a busy year is actually a profitable one.", "scene": "define",
     "c": {"eyebrow": "The real gap", "term": "Every list answers lead capture. None answer job economics.", "body": "How do I run the numbers on the work I already booked? That question has no tool on any current list."}},

    # ---------- CH7 — adoption gap ----------
    {"vo": "Seventh — how many contractors are actually using AI in 2026?", "scene": "chapter", "c": {"num": "07", "title": "The adoption gap"}},
    {"vo": "A survey of a thousand residential contractors found seventy four percent see AI as key to running the business efficiently. Only about twenty five percent are actually using it today. That's a fifty-point gap between believing it matters and doing anything about it.", "scene": "stat",
     "c": {"value": "74% see it, 25% use it", "label": "Residential contractors, surveyed 2026 — the gap between interest and adoption", "source": "ServiceTitan, 2026 Residential State of the Trades Report"}},

    # ---------- CH8 — do you have to replace anything ----------
    {"vo": "Eighth — do you have to replace your AI receptionist to add a back-office AI tool? No. They solve different problems and were never built to compete with each other.", "scene": "chapter", "c": {"num": "08", "title": "Replace it, or stack it?"}},
    {"vo": "Front office answers and books the job. Field diagnostics supports the tech once they're on-site. Back office runs the numbers after the job is already booked — pricebook, AR priority, dispatch margin, job cost, the weekly scorecard. Three layers, stacked, not swapped.", "scene": "process",
     "c": {"title": "Three layers of the same business", "steps": [
         "Front office answers and books the job",
         "Field diagnostics supports the tech on-site",
         "Back office runs the numbers after it's booked",
         "Each layer solves a different problem",
         "Stacking beats swapping"]}},
    {"vo": "And here's why the back office has to be its own layer. ServiceTitan's own AI reads ServiceTitan data only. QuickBooks Online has zero visibility into ServiceTitan's job and dispatch data. Collections, job costing, and a real KPI scorecard all need numbers that live in both places at once.", "scene": "define",
     "c": {"eyebrow": "Why it can't just be a ServiceTitan feature", "term": "ServiceTitan's AI and QuickBooks don't talk to each other", "body": "A back-office layer has to read both systems, because the numbers that matter live split across them."}},

    # ---------- CH9 — where Top Builder AI fits ----------
    {"vo": "Ninth — how does Top Builder AI fit into this landscape?", "scene": "chapter", "c": {"num": "09", "title": "Where Top Builder AI fits"}},
    {"vo": "As the back-office row none of these lists have. It doesn't compete with an AI receptionist or with Titan Intelligence — it picks up exactly where they stop. Pricebook, collections, dispatch margin, job costing, and reporting, mapped to the ServiceTitan and QuickBooks setup you already run.", "scene": "define",
     "c": {"eyebrow": "The missing row", "term": "Top Builder AI is the back office, not another front office", "body": "Pricebook, collections, dispatch margin, job costing, reporting — scoped to your actual ServiceTitan and QuickBooks setup."}},

    # ---------- CTA ----------
    {"vo": "If every AI tool on your shortlist so far answers the phone but not the pricebook, the collections queue, or the dispatch margin call, that's the gap a Top Builder AI Teardown maps against your own setup. Book a thirty-minute fit call and see it run on your own data.", "scene": "cta",
     "c": {"eyebrow": "Top Builder AI · the back-office row", "title": "Missing the Back-Office Row on Your Shortlist?", "sub": "Map it against your own ServiceTitan and QuickBooks setup", "url": "book.topbuilderai.com"}},
]

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    secs = ae.render_body(B, OUT, CACHE)
    print(f"BODY {secs:.1f}s ({secs/60:.1f} min), {len(B)} beats -> {OUT}")
