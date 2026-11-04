"""Assemble the Supabase-ready blog_posts record for the fractional-CFO-cost post.
Validates: ZERO em/en dashes anywhere; FAQ count 12-18; FAQ answers 40-80 words; emits JSON.
Does NOT insert (gated mode)."""
import json, re, pathlib

HERE = pathlib.Path(__file__).parent
content = (HERE / "post_fractional-cfo-cost.html").read_text(encoding="utf-8").strip()

slug = "fractional-cfo-cost-construction-company"
title = "What Does a Fractional CFO Cost for a Construction Company? (2026)"

faq = [
    {"question": "What is the average cost of a fractional CFO for a construction company?",
     "answer": "The average is $3,000 to $9,000 per month for an ongoing retainer, based on published construction-specialist cost guides from nStar Finance, CFO Advisors, Madras Accountancy, and The Cashflow CFO (2026). One-time diagnostics run $2,500 to $10,000, and fixed-scope cleanup projects run $5,000 to $15,000. The exact figure depends on your revenue and how much ongoing work is involved."},
    {"question": "How much does a full-time construction CFO cost compared to fractional?",
     "answer": "A full-time construction CFO costs roughly $170,000 to $360,000 per year all-in, according to CFMA (2025) compensation surveys. A fractional retainer at $5,000 per month is about $60,000 per year for comparable judgment on the slice of time you need. For most contractors doing $1M to $25M, fractional is the only version the math allows."},
    {"question": "Why do fractional CFOs charge a monthly retainer instead of hourly?",
     "answer": "A fixed monthly fee aligns the relationship. Hourly billing makes a contractor hesitate to ask questions, which is the opposite of what a CFO partnership should reward. A retainer covers ongoing forecasting, job-cost oversight, and bank strategy without a meter running. Hourly rates do exist, usually $150 to $450 per hour, but most contractors do better on a flat monthly fee."},
    {"question": "Is a fractional CFO worth it for a small contractor under $5M?",
     "answer": "Usually yes. The cost of not knowing your numbers is larger than the fee. The average general contractor nets only 5% to 6% margin while top performers reach 10% to 12% (industry benchmarks, 2026). Recovering a single point of margin on a $5M contractor is $50,000, which clears a typical annual retainer many times over."},
    {"question": "What does a construction fractional CFO actually do day to day?",
     "answer": "The core deliverables are a trustworthy job-cost report, a WIP schedule showing over- and under-billings, a 13-week cash forecast, and a monthly close that produces bank-ready and surety-ready statements. Beyond reporting, the CFO makes the calls a contractor cannot delegate: which jobs to take, when to buy or finance equipment, and how much backlog payroll can safely support."},
    {"question": "How is a fractional CFO different from a bookkeeper or controller?",
     "answer": "They work at three altitudes. A bookkeeper records transactions. A controller keeps those records accurate and the close clean. A fractional CFO uses the clean records to look forward: cash strategy, job-level profitability, financing, and high-stakes decisions. You need all three functions, but only the CFO seat is hard to justify full-time at $1M to $25M, which is why buying it fractionally makes sense."},
    {"question": "When should a contractor hire a fractional CFO?",
     "answer": "Hire one when the size of your decisions outgrows the quality of your numbers, usually between $1M and $5M in revenue. Other triggers: a bonding company wants clean reviewed statements, you are preparing to sell or add a partner, or you keep being profitable on paper while the bank account disagrees. If you cannot say which jobs made money last quarter, you are already past due."},
    {"question": "How much should a $10M to $25M construction company pay for a fractional CFO?",
     "answer": "Larger contractors typically pay at the top of the band and above. CFO Advisors lists $5,000 to $10,000 per month for $5M to $20M firms, and Civil CFO lists $10,000 to $15,000 per month for $10M to $70M firms (2026). At this size the work is heavier: more concurrent jobs, bigger draws, and bonding and financing decisions that justify a deeper engagement."},
    {"question": "Does the fractional CFO fee include bookkeeping?",
     "answer": "It depends on the firm. At Salisbury CFO the bookkeeping is handled inside the engagement, so you are not stitching together a separate bookkeeper, controller, and CFO who never talk to each other. Some firms price the CFO seat separately and assume you already have clean books. Always confirm what the retainer covers, because re-doing messy books is often the first real cost."},
    {"question": "What is a 14-Day Financial X-Ray and what does it cost?",
     "answer": "The 14-Day Financial X-Ray is Salisbury CFO's diagnostic. In two weeks it produces a written leak list: the exact gaps in your books, job costing, and cash, with what it would take to close them. It costs $3,500, and is free for contractors at $10M-plus preparing for an exit or PE process. It is a low-friction way to see your real numbers before any retainer."},
    {"question": "How fast does a fractional CFO pay for itself?",
     "answer": "Often within the first engagement. On a $5M contractor, recovering one point of margin is $50,000 against a $60,000 annual retainer. Catching one under-billed change-order package or tightening one slow draw cycle can clear the fee by itself. The 13-week cash forecast alone, by flagging when cash gets tight three months out, frequently prevents a far costlier emergency."},
    {"question": "Do I need a construction-specific fractional CFO or will any CFO do?",
     "answer": "Construction-specific is strongly preferred. Contractor accounting is different enough that the field has its own association, CFMA. Revenue arrives in draws held back by retainage, costs land on jobs out of sync with billing, and profit is recognized over months by percentage-of-completion. A generalist CFO who has never managed WIP will miss the exact things that sink contractors, so industry experience matters more here than in most fields."},
    {"question": "What guarantee comes with a fractional CFO engagement?",
     "answer": "Guarantees vary by firm and many offer none. Salisbury CFO backs the relationship with a 3x-or-you-don't-pay promise: the engagement returns at least three times its cost in recovered margin, recovered cash, or avoided loss, or you do not pay. That structure works because at a $1M to $25M contractor, the financial leaks are almost always larger than the fee."},
]

key_takeaways = [
    "A construction fractional CFO costs about $3,000 to $9,000 per month for an ongoing retainer (nStar, CFO Advisors, Madras, The Cashflow CFO, 2026).",
    "A full-time construction CFO costs $170,000 to $360,000 per year all-in (CFMA 2025), so fractional gives you the seat without the salary.",
    "Price follows the depth of work: a diagnostic, a fixed sprint, and an ongoing retainer are three different prices for three different jobs.",
    "The Salisbury CFO ladder is at market on every rung: X-Ray $3,500, 6-Week Sprint $9,800 to $14,500, Command Retainer $3,500 to $12,000 per month (up to $15M+ at $9,000 to $12,000).",
    "For most $1M to $25M contractors the fee is small next to the leaks it closes, which is why a 3x-or-you-don't-pay guarantee can stand behind it.",
]

excerpt = ("A construction fractional CFO costs about $3,000 to $9,000 per month for a retainer, "
           "versus $170,000 to $360,000 per year for a full-time hire (CFMA 2025). Here is the honest "
           "breakdown by engagement type, when it is worth it, and how the Salisbury CFO ladder is priced.")

record = {
    "slug": slug,
    "title": title,
    "excerpt": excerpt,
    "content": content,
    "cover_image": None,  # set to /blog/<slug>-cover after thumbnail review
    "category": "Fractional CFO",
    "author": "Cory Salisbury",
    "reading_minutes": 12,
    "tags": ["fractional cfo", "construction cfo", "cfo cost", "construction finance",
             "job costing", "cash flow", "fractional cfo cost"],
    "status": "published",
    "seo_title": "Fractional CFO Cost for a Construction Company (2026 Guide)",
    "seo_description": ("What a fractional CFO costs for a construction company in 2026: $3,000 to "
                        "$9,000 per month, versus $170,000 to $360,000 for a full-time CFO (CFMA). "
                        "Full breakdown by engagement type and when it is worth it."),
    "faq": faq,
    "key_takeaways": key_takeaways,
    "primary_keyword": "fractional cfo cost for construction company",
    "secondary_keywords": ["how much does a fractional cfo cost", "construction cfo cost",
                            "fractional cfo for contractors", "fractional cfo vs full-time cfo cost"],
    "canonical_url": None,
    "schema_type": "BlogPosting",
}

# ---- validation gates ----
errors = []
blob = json.dumps(record, ensure_ascii=False)
for ch, name in [("—", "em-dash"), ("–", "en-dash"), ("‒", "figure-dash"),
                 ("―", "horizontal-bar"), ("−", "minus-sign")]:
    n = blob.count(ch)
    if n: errors.append(f"{name} found {n}x")
if not (12 <= len(faq) <= 18): errors.append(f"FAQ count {len(faq)} not in 12-18")
for i, f in enumerate(faq):
    wc = len(f["answer"].split())
    if not (40 <= wc <= 80): errors.append(f"FAQ[{i}] answer {wc} words (need 40-80): {f['question'][:40]}")

text = re.sub(r"<[^>]+>", " ", content); text = re.sub(r"&[a-z]+;", " ", text)
body_words = len(re.findall(r"\b[\w$%/.-]+\b", text))
faq_words = sum(len(f["question"].split()) + len(f["answer"].split()) for f in faq)
kt_words = sum(len(k.split()) for k in key_takeaways)
total_words = body_words + faq_words + kt_words

print("=== VALIDATION ===")
print("body words:", body_words, "| faq words:", faq_words, "| takeaways:", kt_words,
      "| TOTAL:", total_words)
print("FAQ count:", len(faq))
print("em/en dashes anywhere:", blob.count("—") + blob.count("–"))
if errors:
    print("FAILED:"); [print("  -", e) for e in errors]
else:
    print("ALL GATES PASS")

out = HERE / "post_fractional-cfo-cost.json"
out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
print("WROTE", out)
