"""VALUE VIDEO -- Procore is shipping its own AI agents. Does a Procore contractor still need a
third-party AI back office, or is that redundant now (INFORMATIONAL, sourced). Companion long-form to
landing/blog/procore-agent-studio-vs-third-party-ai.html. Sourced facts, no invented figures: Procore
has described Agent Studio as a way to configure agents that work on Procore's own project, financial
and document data, per Procore's own public statements (the specifics are Procore's to define, so this
script deliberately does not paraphrase a feature list); a 2024 industry payments report found the
large majority of contractors face payment delays beyond thirty days, up sharply from two years prior;
a 2024 Intuit survey of firms with ten to ninety nine employees found an average of twenty five hours a
week spent on manual data entry or reconciling data across apps; Top Builder AI's own FAQ describes a
read only OAuth install, per tenant database isolation, encryption at rest and in transit, inference
only use of customer data, deterministic tested computation with the model only narrating, and a
propose approve execute action gate. No dollar figures of any kind appear anywhere in this script, on
either vendor, per the standing no-price-in-video rule. Adapted from vid_jobber_vs_housecall_pro.py's
proven shape -- image-free scenes throughout (hook/chapter/define/stat/process/checklist/cta), no
missing-asset risk. Renders animated body only. Usage: python vid_procore_agent_studio_vs_third_party.py
"""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)
ae.WORDMARK = "TOP BUILDER AI"  # this video is about the AI agent-orchestration line, not Top Builder OS

CACHE = HERE / "build/val_procore_vs_3p"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = pathlib.Path("C:/Users/you/Downloads/ServiceTitan Agent platform/assets/video/longform/procore-agent-studio-vs-third-party-ai/body.mp4")

B = [
    # ---------- HOOK ----------
    {"vo": "Procore just started shipping its own AI agents through something it calls Agent Studio. So if you're a Procore contractor already evaluating a third-party AI back office, the honest question is whether you still need one, or whether Procore just made it redundant. The answer isn't marketing spin, it's a data question: an AI agent can only act on data it can actually see, and the most consequential back-office data in a construction business doesn't live inside Procore at all. Let's go through exactly what Procore's own AI runs on, what a third-party platform runs on instead, and how those two things actually fit together.", "scene": "hook",
     "c": {"icon": "🤝", "title": "Procore AI & Agent Studio vs a Third-Party Back Office", "sub": "What each one actually covers, straight from the boundary", "pulse": True}},

    # ---------- CH1 -- what Procore's AI is ----------
    {"vo": "First, what is Procore's AI and Agent Studio, in Procore's own words?", "scene": "chapter", "c": {"num": "01", "title": "What Procore's AI actually is"}},
    {"vo": "Procore has said it's building AI across its platform, and it has described Agent Studio as a way for a contractor to configure AI agents that work across Procore's own data and workflows. As of today, the responsible summary is that those capabilities run on Procore's project, financial, and document data, and what ships, what it's named, and what each agent can do are entirely Procore's to define. This video deliberately does not paraphrase a feature list, because it's evolving, and Procore's own current documentation is the right source for the specifics, not a third party's summary.", "scene": "define",
     "c": {"eyebrow": "Procore's own data, Procore's own roadmap", "term": "Agent Studio", "body": "Configurable agents that work across Procore's own project, financial, and document data. What ships is Procore's to define."}},

    # ---------- CH2 -- the boundary is data ----------
    {"vo": "So where does that leave a third-party platform? Is this a competition Procore is now winning by default?", "scene": "chapter", "c": {"num": "02", "title": "The boundary isn't ambition, it's data"}},
    {"vo": "No, and the reason is structural. Procore's platform holds the project record: budgets, prime contracts, commitments, change orders, direct costs, invoicing, RFIs, submittals, daily logs, documents. Any AI Procore builds has first-class access to that record, and that's a genuine advantage inside it. But an agent can only act on data it can see, and the general ledger a lender, a bonding agent, or a partner actually trusts doesn't live inside Procore's data at all. It lives in QuickBooks.", "scene": "define",
     "c": {"eyebrow": "Not a quality gap", "term": "What Procore's AI can see", "body": "Budgets, contracts, commitments, change orders, documents, RFIs. All inside Procore's own data."}},

    # ---------- CH3 -- what lives outside ----------
    {"vo": "So what specifically lives outside Procore's data, in that ledger?", "scene": "chapter", "c": {"num": "03", "title": "What lives outside Procore's data"}},
    {"vo": "Four ordinary back-office jobs, all of them. The A/R follow-up question isn't what did we bill in Procore, it's what has actually not been paid, according to the ledger and the bank. The A/P question starts with a vendor bill sitting in an email inbox and ends with a posted entry in QuickBooks. The margin question is only answerable once the project record and the ledger are reconciled against each other. And the payroll question, is the overtime math right, do claimed hours match clocked hours, lives in timesheets and pay rules, not in a project workflow.", "scene": "checklist",
     "c": {"title": "The four jobs outside Procore's data", "items": ["A/R follow-up against the ledger and the bank, not the Procore bill", "A/P: an emailed vendor bill becoming a posted QuickBooks entry", "Margin, once the project record and the ledger reconcile", "Payroll: claimed hours vs clocked hours, pay-rule math"]}},

    # ---------- CH4 -- payment delay stat ----------
    {"vo": "How big is that first gap, the unpaid A/R sitting in the ledger?", "scene": "chapter", "c": {"num": "04", "title": "How bad is the collections gap, really?"}},
    {"vo": "Bad, and getting worse. A 2024 construction payments report found that eighty two percent of contractors reported payment delays of more than thirty days, up from just forty nine percent two years earlier. That's a sharp jump in a short window, and it's happening on the ledger side, the side no project-data AI can see, because the record of what actually got paid lives in the bank and in QuickBooks, not in a Procore invoice status.", "scene": "stat",
     "c": {"value": "82%", "label": "of contractors reported payment delays over 30 days in 2024, up from 49% two years earlier", "source": "Rabbet 2024 Construction Payments Report"}},

    # ---------- CH5 -- reconciliation hours stat ----------
    {"vo": "And the manual reconciliation burden underneath all of that -- how much time does it actually eat?", "scene": "chapter", "c": {"num": "05", "title": "The reconciliation tax, measured"}},
    {"vo": "A 2024 Intuit QuickBooks survey of firms with ten to ninety nine employees found those businesses spend an average of twenty five hours a week on manual data entry or reconciling data across apps. That's the better part of a full-time role, every single week, just keeping two systems roughly in agreement, and none of that time shows up as a line item on a Procore project dashboard.", "scene": "stat",
     "c": {"value": "25 hrs/week", "label": "average time firms with 10-99 employees spend on manual data entry or cross-app reconciliation", "source": "Intuit QuickBooks Business Solutions Survey, 2024"}},

    # ---------- CH6 -- what a third-party platform runs ----------
    {"vo": "So what does a third-party back-office platform actually run, given all of that?", "scene": "chapter", "c": {"num": "06", "title": "What Top Builder AI actually runs"}},
    {"vo": "It installs alongside Procore, reads its data through the official read-only OAuth integration, reads the books through QuickBooks Online, and runs the ledger-side back office. On Procore today that's five agents: Workforce, Routing, Documents, Financial, and Collections, plus a Pricebook engine fed by vendor price files you upload. Booking and Inventory stay ServiceTitan-only, because Procore exposes no customer-intake or inventory feed, and scoping that honestly matters more than claiming coverage that doesn't exist.", "scene": "define",
     "c": {"eyebrow": "Alongside Procore, not inside it", "term": "Five agents on Procore today", "body": "Workforce, Routing, Documents, Financial, Collections -- plus a Pricebook engine on uploaded vendor files."}},

    # ---------- CH7 -- side by side comparison ----------
    {"vo": "Put the two side by side, dimension by dimension. Where does each one actually cover the work?", "scene": "chapter", "c": {"num": "07", "title": "Side by side, dimension by dimension"}},
    {"vo": "On collections against the A/R ledger, Procore's agents don't reach it, because follow-up against the ledger and the bank sits outside Procore's data; a third-party Collections agent works that aging list around the clock, with every send needing a lead's approval. On A/P from an emailed vendor bill, same story: the inbox and the QuickBooks entry are outside Procore's data, so a Documents agent drafts that entry for a finance lead to approve. On payroll checks, the pay-rule math lives outside the project record, so a Workforce agent flags overtime and payroll gaps before payday.", "scene": "checklist",
     "c": {"title": "Where the third-party layer picks up", "items": ["A/R collections: works the aging list, human approves every send", "A/P drafting: turns an emailed bill into a QuickBooks entry to approve", "Payroll: flags overtime and claimed-vs-clocked gaps before payday", "The books: reconciles what Procore says a job cost against QuickBooks"]}},
    {"vo": "On how the figures get produced and how actions get taken, the same standard applies on both sides of this comparison, and it's worth naming plainly: every number a third-party agent shows comes from deterministic, tested code, never a language-model guess, and every action runs through a propose, approve, execute gate that's reversible and fully audited. That's not a claim unique to us, it's the bar any AI touching your books should have to clear.", "scene": "define",
     "c": {"eyebrow": "The bar for either layer", "term": "How figures should be produced", "body": "Deterministic, tested computation. The model narrates; it never computes. Every action is proposed, approved, and audited."}},

    # ---------- CH8 -- sync vs reconciliation ----------
    {"vo": "Some tools already claim to bridge Procore and QuickBooks by syncing them. Doesn't that solve this?", "scene": "chapter", "c": {"num": "08", "title": "A sync tool isn't the same thing as reconciliation"}},
    {"vo": "No, and the difference matters. A sync tool addresses the plumbing: it moves records from one system to the other on a schedule. That's useful, and it is not reconciliation. Moving a record doesn't tell you the two systems disagree, by how much, or why, and it certainly doesn't tell you what to do about it. Worse, a sync running on top of unreconciled data faithfully copies the noise in both directions, week after week.", "scene": "define",
     "c": {"eyebrow": "One sentence, the whole difference", "term": "Sync vs. reconciliation", "body": "A sync moves records. Reconciliation tells you where they disagree, why, and drafts the next action for a person to approve."}},

    # ---------- CH9 -- why they drift ----------
    {"vo": "Why do Procore and QuickBooks even drift apart in the first place?", "scene": "chapter", "c": {"num": "09", "title": "Why the two systems drift, mechanically"}},
    {"vo": "For ordinary, nobody's-fault reasons. A commitment exists in Procore before its bill ever posts in QuickBooks. An owner payment lands in the bank and gets deposited in QuickBooks without being applied to the matching Procore invoice. Retainage gets carried one way in the project platform and another way in the ledger. A change order gets approved in one system during a busy week and never gets mirrored in the other. None of that is anyone's fault -- it's what happens when two systems describe the same money on two different schedules.", "scene": "checklist",
     "c": {"title": "Why the drift happens, mechanically", "items": ["A commitment posts in Procore before its bill hits QuickBooks", "A bank deposit lands unapplied to the matching Procore invoice", "Retainage is tracked one way in the project platform, another in the ledger", "A change order gets approved in one system and never mirrored in the other"]}},

    # ---------- CH10 -- run both together ----------
    {"vo": "Given all of that, can a contractor actually run Procore's AI and a third-party platform together, or does it have to be one or the other?", "scene": "chapter", "c": {"num": "10", "title": "Running both together, not choosing one"}},
    {"vo": "Together, and that's the setup we expect becomes normal. Keep Procore as the system of record and adopt whatever Procore AI features fit your project workflows as they ship. Add the third-party layer for the QuickBooks-ledger back office. Because a third-party platform like Top Builder AI connects read-only and never writes to Procore without an explicit, human-approved action, there's nothing to conflict: both layers read the same project record and act in entirely different places.", "scene": "define",
     "c": {"eyebrow": "Not a switch, an addition", "term": "Both layers, at once", "body": "Procore stays the system of record. The third-party layer reads it read-only and acts only on the ledger side, human-approved."}},

    # ---------- CH11 -- data safety ----------
    {"vo": "Before any of this is worth considering, what does a contractor need to know about handing a third-party AI read access to Procore and QuickBooks data at all?", "scene": "chapter", "c": {"num": "11", "title": "The data-safety posture, checked"}},
    {"vo": "This is the part worth verifying rather than trusting. Read-only OAuth by default, meaning it can see the data but can't write to your system of record without a separate, explicit, human-approved action. Per-tenant isolation enforced at the database level, so one contractor's data structurally can't leak into another's. Encryption at rest and in transit. And a strict rule that customer data gets used for inference only, meaning to generate that specific answer, never to train a model on your numbers.", "scene": "checklist",
     "c": {"title": "What to actually verify before connecting anything", "items": ["Read-only OAuth by default -- can't write without an approved action", "Per-tenant isolation enforced at the database level", "Encryption at rest and in transit", "Customer data used for inference only -- never to train a model"]}},

    # ---------- CH12 -- how to decide ----------
    {"vo": "So how should a Procore contractor actually decide what they need, between the two?", "scene": "chapter", "c": {"num": "12", "title": "How to decide what your shop actually needs"}},
    {"vo": "Ask where the pain actually lives. If the friction is inside the project, coordination, document workflows, the day-to-day of running jobs in Procore, start with Procore's own AI and its Agent Studio tooling, and judge it against Procore's current documentation. If the pain is in the books, an aging list nobody works, a ledger that disagrees with the project record, bills waiting in an inbox, payroll running on trust, that work lives outside Procore's data, and it's exactly what a third-party back-office layer runs. Plenty of shops have both kinds of pain at once, and in that case the answer is both layers, not a choice between them.", "scene": "process",
     "c": {"title": "Where to start, based on where it hurts", "steps": ["Pain inside the project or document workflow -> start with Procore's own AI", "Pain in the books, the aging list, payroll trust -> a third-party ledger layer", "Both kinds of pain at once -> both layers, not a choice", "Judge each against its own current documentation, not a paraphrase"]}},

    # ---------- CH13 -- not a competitive pitch ----------
    {"vo": "Is any of this actually a pitch to replace Procore's AI, dressed up as an honest comparison?", "scene": "chapter", "c": {"num": "13", "title": "This isn't a Procore replacement pitch"}},
    {"vo": "No, and it's worth conceding plainly. If your question lives inside Procore's data, project workflows, coordination, document handling within the platform, anything where the record and the action both live in Procore, Procore's own AI is the natural first answer, and configuring it through Procore's own tooling keeps you inside a platform you already trust. A third-party layer doesn't compete there, and a comparison pretending otherwise wouldn't be worth your time.", "scene": "define",
     "c": {"eyebrow": "Said plainly, not as a hedge", "term": "What belongs to Procore", "body": "Anything where the record and the action both live inside Procore's own data. That's Procore's answer, first."}},

    # ---------- CTA ----------
    {"vo": "So here's the fastest way to check where you actually stand, tonight. Pull up your real QuickBooks aging list next to what Procore shows for the same jobs, and see if the two numbers agree. If they don't, or if you honestly don't know because nobody's ever put them side by side, that's the exact gap this video walked through -- and it's the one a reconciliation-first, human-approved layer is built to close, running alongside whatever Procore's own AI ends up shipping.", "scene": "cta",
     "c": {"eyebrow": "Put the ledger and the project record side by side, tonight", "title": "Does Your Procore Data Actually Agree With Your Real Books?", "sub": "Most shops have never checked -- a fit call walks through what turns up in yours", "url": "topbuilderai.com"}},
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
