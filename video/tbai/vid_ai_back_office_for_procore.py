"""VALUE VIDEO -- What is an AI back office for Procore, and how does it reconcile Procore to a
contractor's actual QuickBooks books (INFORMATIONAL, sourced). Companion long-form to
landing/blog/ai-back-office-for-procore.html. Sourced facts, no invented figures: a 2024 Intuit
QuickBooks survey of firms with ten to ninety nine employees found an average of twenty five hours a
week spent on manual data entry or reconciling data across apps; a 2024 industry payments report found
the large majority of contractors face payment delays beyond thirty days, up sharply from two years
prior; a 2026 AGC analysis of federal producer-price data found copper and brass mill shape prices up
over fifteen percent in the trailing twelve months; Top Builder AI's own FAQ describes a read only
OAuth install, per tenant database isolation, encryption at rest and in transit, inference only use of
customer data, deterministic tested computation with the model only narrating, and a propose approve
execute action gate. No dollar figures of any kind appear anywhere in this script, per the standing
no-price-in-video rule (not even the industry loss estimate from the same payments report -- only the
percentage is used). Adapted from vid_procore_agent_studio_vs_third_party.py's proven shape --
image-free scenes throughout (hook/chapter/define/stat/checklist/process/cta), no missing-asset risk.
Renders animated body only; no on-topic Procore bookend exists yet (see plan notes), so the assembled
video is the body alone. Usage: python vid_ai_back_office_for_procore.py
"""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)
ae.WORDMARK = "TOP BUILDER AI"

CACHE = HERE / "build/val_aibackoffice_procore"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = pathlib.Path("C:/Users/you/Downloads/ServiceTitan Agent platform/assets/video/longform/ai-back-office-for-procore/body.mp4")

B = [
    # ---------- HOOK ----------
    {"vo": "If you run projects in Procore and keep your books in QuickBooks, here's the real question worth asking: what actually reconciles those two systems, and who's working your unpaid invoices while you're focused on the job site? Procore is genuinely excellent at running the project, the budgets, the commitments, the change orders, the RFIs. But it was never built to run your general ledger, and the general ledger is what a lender, a bonding agent, or a partner actually trusts. An AI back office for Procore is a set of self-learning agents that install alongside the Procore you already run, reconciled to your actual QuickBooks books. Let's walk through exactly what that means, what it isn't, and how it stays safe.", "scene": "hook",
     "c": {"icon": "🏗️", "title": "The AI Back Office for Procore", "sub": "Reconciled to your actual QuickBooks books", "pulse": True}},

    # ---------- CH1 -- what it is ----------
    {"vo": "First, what exactly is an AI back office for Procore?", "scene": "chapter", "c": {"num": "01", "title": "What an AI back office for Procore actually is"}},
    {"vo": "It's intelligence installed alongside the platform you already run, not a replacement for it. Procore stays the system of record for the project: the budget, the commitments, the change orders, the daily logs. The back-office layer reads that data through Procore's official read-only OAuth integration, reads your books through QuickBooks Online, and runs the analysis neither system runs on its own: collections, A/P drafting, payroll checks, document filing, and material re-costing. Every finding becomes a recommendation a person approves.", "scene": "define",
     "c": {"eyebrow": "Alongside Procore, not instead of it", "term": "AI back office for Procore", "body": "Self-learning agents installed next to the Procore you run, reconciled to your actual QuickBooks general ledger."}},

    # ---------- CH2 -- where the numbers come from ----------
    {"vo": "And where do the actual numbers come from?", "scene": "chapter", "c": {"num": "02", "title": "Where the numbers actually come from"}},
    {"vo": "From the ledger, not the project platform. Your books, the number a lender or a bonding agent actually trusts, live in QuickBooks, not in Procore. So an honest AI back office reconciles to the QuickBooks ledger rather than reporting on project data alone. Every figure it produces is computed by deterministic, unit-tested code; the language model only writes the plain-English explanation and never computes a number. Same inputs, same figure, every time, auditable.", "scene": "define",
     "c": {"eyebrow": "Not project data alone", "term": "Where the figures come from", "body": "Deterministic, tested code computes every number. The model only narrates it, and never touches the math."}},

    # ---------- CH3 -- reconciliation hours stat ----------
    {"vo": "How much manual work is actually going into keeping these two systems in rough agreement?", "scene": "chapter", "c": {"num": "03", "title": "The reconciliation tax, measured"}},
    {"vo": "More than you'd guess. A 2024 Intuit QuickBooks survey of firms with ten to ninety nine employees found those businesses spend an average of twenty five hours a week on manual data entry or reconciling data across apps. That's the better part of a full-time role, every single week, just keeping two systems roughly in agreement. For a Procore contractor, that's the hours spent keying vendor bills, matching payments, and rebuilding job-cost truth across two systems by hand.", "scene": "stat",
     "c": {"value": "25 hrs/week", "label": "average time firms with 10-99 employees spend on manual data entry or cross-app reconciliation", "source": "Intuit QuickBooks Business Solutions Survey, 2024"}},

    # ---------- CH4 -- fits alongside Procore ----------
    {"vo": "So where does this actually fit next to Procore, without stepping on what Procore already does well?", "scene": "chapter", "c": {"num": "04", "title": "Where it fits next to Procore"}},
    {"vo": "Procore is one of the most capable construction management platforms in the industry, and it should stay your system of record. Its budgets, prime contracts, commitments, and invoicing are strong, and Procore is building its own AI on top of that project data too, as of today, on its own roadmap. We don't compete there. An AI back office fits in the space Procore's data doesn't reach: the QuickBooks ledger, the A/R follow-up, the vendor-bill inbox sitting in email, and the payroll check nobody has time to run by hand.", "scene": "define",
     "c": {"eyebrow": "Not a Procore replacement", "term": "The scope, stated plainly", "body": "Procore keeps the project record. The back office covers the ledger, collections, A/P, and payroll instead."}},

    # ---------- CH5 -- payment delay stat ----------
    {"vo": "How big is the collections gap specifically, the unpaid invoices sitting in the ledger?", "scene": "chapter", "c": {"num": "05", "title": "How bad is the collections gap?"}},
    {"vo": "Bad, and getting worse. A 2024 construction payments report found that eighty two percent of contractors reported payment delays of more than thirty days, up from just forty nine percent two years earlier. That's a sharp jump in a short window, and it's happening on the ledger side, the side a project-data tool alone can't see, because what actually got paid lives in the bank and in QuickBooks, not in a Procore invoice status.", "scene": "stat",
     "c": {"value": "82%", "label": "of contractors reported payment delays over 30 days in 2024, up from 49% two years earlier", "source": "Rabbet 2024 Construction Payments Report"}},

    # ---------- CH6 -- why they drift ----------
    {"vo": "Why do Procore and QuickBooks even drift apart in the first place?", "scene": "chapter", "c": {"num": "06", "title": "Why the two systems drift, mechanically"}},
    {"vo": "For ordinary, nobody's-fault reasons. A commitment exists in Procore before its bill ever posts to QuickBooks. An owner payment lands in the bank and gets deposited in QuickBooks without being applied to the matching Procore invoice. Retainage gets carried one way in the project platform and another way in the ledger. A change order gets approved in one system during a busy week and never gets mirrored in the other. None of that is anyone's fault, it's what happens when two systems describe the same money on two different schedules.", "scene": "checklist",
     "c": {"title": "Why the drift happens, mechanically", "items": ["A commitment posts in Procore before its bill hits QuickBooks", "A bank deposit lands unapplied to the matching Procore invoice", "Retainage is tracked one way in the project platform, another in the ledger", "A change order is approved in one system and never mirrored in the other"]}},

    # ---------- CH7 -- sync vs reconciliation ----------
    {"vo": "Doesn't a sync tool that already connects Procore and QuickBooks solve this for you?", "scene": "chapter", "c": {"num": "07", "title": "A sync tool isn't reconciliation"}},
    {"vo": "No, and the difference matters. A sync tool addresses the plumbing, it moves records from one system to the other on a schedule. That's useful, and it is not the same thing as reconciliation. Moving a record doesn't tell you the two systems disagree, by how much, or why, and it certainly doesn't tell you what to do about it. Worse, a sync running on top of unreconciled data faithfully copies the noise in both directions, week after week.", "scene": "define",
     "c": {"eyebrow": "One sentence, the whole difference", "term": "Sync vs. reconciliation", "body": "A sync moves records between Procore and QuickBooks. Reconciliation tells you where they disagree, why, and drafts the next action for a person to approve."}},

    # ---------- CH8 -- the agents ----------
    {"vo": "So which agents actually run this back office for a Procore contractor, day to day?", "scene": "chapter", "c": {"num": "08", "title": "The agents that run the back office"}},
    {"vo": "The Financial agent computes GAAP-correct job profitability, over-billing and under-billing per job, and a thirty, sixty, ninety day cash forecast, reconciled to your actual QuickBooks ledger. It's also the agent that runs the Procore-to-QuickBooks reconciliation itself, turning every mismatch into a worklist item instead of a mystery.", "scene": "define",
     "c": {"eyebrow": "Money", "term": "The Financial agent", "body": "Job profitability, over- and under-billing, a rolling cash forecast, and the Procore-to-QuickBooks reconciliation itself."}},
    {"vo": "The Collections agent works the accounts-receivable aging list around the clock: correct due-date aging, a worst-first queue, and drafted outreach. Every send still requires a department lead's approval, even in auto mode. It never moves money or sends anything on its own.", "scene": "define",
     "c": {"eyebrow": "A/R", "term": "The Collections agent", "body": "Works the aging list around the clock and drafts outreach. Every send still needs a lead's approval."}},
    {"vo": "The Documents agent classifies and routes every inbound document and vendor bill to the right project and folder, drafts the A/P entry buried in an emailed bill for your finance lead to approve, and flags anything needing a signature or a certificate of insurance expiring soon.", "scene": "define",
     "c": {"eyebrow": "Paperwork", "term": "The Documents agent", "body": "Routes inbound paperwork, drafts the A/P entry from an emailed bill, and flags expiring certificates of insurance."}},
    {"vo": "The Workforce agent forecasts understaffing and avoidable overtime by trade and week before the week happens, and checks payroll before it runs, the overtime math and the claimed-versus-clocked gaps that quietly inflate a payroll run. Adjustments always require a lead's approval.", "scene": "define",
     "c": {"eyebrow": "People", "term": "The Workforce agent", "body": "Forecasts overtime risk and checks payroll before it runs. Every adjustment still needs a lead's approval."}},
    {"vo": "The Routing and Dispatch agent hands your scheduler skill-correct, drive-time-optimized crew assignments and a severity-triaged board. It's fully advisory by design, it owns no gated actions, and your scheduler accepts or overrides every suggestion in the field.", "scene": "define",
     "c": {"eyebrow": "Advisory", "term": "Routing & Dispatch", "body": "Drive-time-optimized crew assignments your scheduler accepts or overrides. No gated actions of its own."}},
    {"vo": "And because Procore has no pricebook of its own, the Pricebook engine runs entirely on vendor price files you upload, re-costing materials to the cent as vendor prices change and proposing each update for a human to approve. With copper and brass mill shape prices up more than fifteen percent in the twelve months ending January twenty twenty six, per an AGC analysis of federal producer-price data, estimating off last year's costs is a quiet margin leak.", "scene": "stat",
     "c": {"value": "15%+", "label": "increase in copper and brass mill shape prices, 12 months ending January 2026", "source": "AGC analysis of BLS Producer Price Index data, 2026"}},

    # ---------- CH9 -- safety ----------
    {"vo": "How does this stay safe when AI is actually touching your books?", "scene": "chapter", "c": {"num": "09", "title": "How it stays safe near your books"}},
    {"vo": "Four guardrails carry the weight. Advisory by default, the agents read and propose, and nothing writes until you enable it, agent by agent. Human-approved actions, money and legal moves always run through a propose, approve, execute gate, with a department lead required. Reversible with an audit trail, every executed action stores the prior state and can be undone to exactly what it was. And deterministic figures, every dollar amount is computed by tested code, never by the model, which only explains the result.", "scene": "checklist",
     "c": {"title": "The four guardrails that carry the weight", "items": ["Advisory by default -- nothing writes until you enable it, agent by agent", "Human-approved actions -- money and legal moves always need a lead", "Reversible with an audit trail -- every action can be undone", "Deterministic figures -- tested code computes every dollar, never the model"]}},

    # ---------- CH10 -- install ----------
    {"vo": "How is this actually installed, and how long does that take?", "scene": "chapter", "c": {"num": "10", "title": "How it's installed, start to finish"}},
    {"vo": "Days, not months, and there's no rip-and-replace. You authorize the app from Procore through a standard OAuth consent flow, seeing exactly which read scopes it requests, and Procore issues the token, no passwords shared. You connect QuickBooks Online next; that accounting connection activates for your account during install, and until it does, the financial agents fail closed rather than guess. The agents start in advisory mode, so you see the reconciliation findings, the aging queue, and the payroll flags on your own data before anything acts. Then you enable human-approved actions agent by agent, on your own timeline.", "scene": "process",
     "c": {"title": "Four steps, measured in days not months", "steps": ["Authorize from Procore -- a standard OAuth flow, exact read scopes shown", "Connect QuickBooks Online -- financial agents fail closed until it's live", "Start in advisory mode -- see the findings on your own data first", "Enable actions agent by agent, on your own timeline"]}},

    # ---------- CH11 -- fit signals ----------
    {"vo": "Is this actually the right fit for your Procore shop, or is that just a sales answer?", "scene": "chapter", "c": {"num": "11", "title": "Is this actually the right fit?"}},
    {"vo": "Ask yourself three honest questions. Does your receivables list only get worked when someone happens to remember? Does the number Procore reports for a job disagree with what QuickBooks actually posted, and nobody can say why quickly? And are your material estimates still riding on last year's vendor prices? If two of those sound familiar, the fit is worth checking. If none of them do, you may not need this yet, and that's a fine answer too.", "scene": "define",
     "c": {"eyebrow": "Three honest signals", "term": "When it's worth checking", "body": "Aging worked only when remembered, Procore and QuickBooks disagreeing, or estimates riding on stale prices."}},

    # ---------- CH12 -- what it isn't ----------
    {"vo": "And what is this deliberately not?", "scene": "chapter", "c": {"num": "12", "title": "What this deliberately isn't"}},
    {"vo": "It isn't a fully autonomous system that acts without you, a human stays in the loop by design, on every dollar and every send. And on Procore specifically, Booking and Inventory stay ServiceTitan-only today, because Procore exposes no customer-intake or inventory feed for those agents to read. We'd rather scope that honestly, in public, than claim coverage that isn't actually there.", "scene": "define",
     "c": {"eyebrow": "Said plainly, not a hedge", "term": "What it isn't", "body": "Not a fully autonomous system, and not full eight-agent coverage on Procore. The gaps are stated, not hidden."}},

    # ---------- CH13 -- bottom line ----------
    {"vo": "So what's the actual bottom line here?", "scene": "chapter", "c": {"num": "13", "title": "The bottom line"}},
    {"vo": "Procore runs the project, and it should keep running it. The under-served work is the QuickBooks-ledger back office: collections, reconciliation, A/P drafting, payroll checks, and material re-costing, running alongside the Procore you already use. Advisory by default, human-approved, reversible, and built on figures that come from tested code, never a model's guess.", "scene": "define",
     "c": {"eyebrow": "In one paragraph", "term": "The bottom line", "body": "Procore keeps the project. The back office covers the ledger, human-approved and built on tested code."}},

    # ---------- CTA ----------
    {"vo": "So here's the fastest way to check where you actually stand, tonight. Pull up your real QuickBooks aging list next to what Procore shows for the same jobs, and see if the two numbers agree. If they don't, or if you honestly don't know because nobody's ever put them side by side, that's the exact gap this video just walked through, and it's the one a reconciliation-first, human-approved back office is built to close.", "scene": "cta",
     "c": {"eyebrow": "Put the ledger and the project record side by side, tonight", "title": "Does Your Procore Data Actually Agree With Your Real Books?", "sub": "Most Procore shops have never checked -- a fit call walks through what turns up in yours", "url": "topbuilderai.com"}},
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
