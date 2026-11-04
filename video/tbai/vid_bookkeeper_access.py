"""VALUE VIDEO — How do you give a bookkeeper or CPA access to your books without handing
over admin? (INFORMATIONAL, sourced). Companion long-form to
landing/blog/accountant-bookkeeper-access-contractor-books.html. Same sourced facts: QuickBooks
Online's Accountant user is functionally near-admin with no dial to turn down (Intuit's own docs +
Community threads); ServiceTitan's Accounting role can't touch payroll by default but CAN edit the
pricebook by default; Standard user + Limited categories is QBO's real narrow path; Advanced (the
priciest QBO tier, after the Aug 2026 price hike) is the only tier with granular custom roles; neither vendor's
permission system talks to the other. Adapted from vid_realtime_job_cost_tracking.py's proven shape —
image-free scenes throughout (hook/chapter/define/stat/process/checklist/cta), no missing-asset risk.
Renders animated body only. Usage: python vid_bookkeeper_access.py
"""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("ae", str(HERE / "anim_engine.py"))
ae = importlib.util.module_from_spec(spec); spec.loader.exec_module(ae)

CACHE = HERE / "build/val_bookkeeper_access"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = pathlib.Path("C:/Users/you/Downloads/ServiceTitan Agent platform/assets/video/longform/bookkeeper-access/body.mp4")

B = [
    # ---------- HOOK ----------
    {"vo": "Your bookkeeper just asked for login access to QuickBooks and ServiceTitan, and you're staring at the invite screen at eleven at night trying to figure out what you're actually about to hand her. Neither QuickBooks Online nor ServiceTitan gives you a single, ready-made bookkeeper role that just works the way most contractors expect. Get the wrong one and she can undo your reconciliations, rewrite your pricebook, or both, without you ever meaning to grant that. So let's go through exactly what each vendor's own documentation says a bookkeeper role can and can't do, where the two platforms quietly disagree on what safe even means, and what actually closes the gap for a shop running both.", "scene": "hook",
     "c": {"icon": "🔐", "title": "What are you actually handing your bookkeeper?", "sub": "What QuickBooks and ServiceTitan's own docs say about bookkeeper access", "pulse": True}},

    # ---------- CH1 — QBO Accountant user ----------
    {"vo": "First question: does adding a bookkeeper in QuickBooks Online mean handing over the keys to everything?", "scene": "chapter", "c": {"num": "01", "title": "Does QuickBooks access mean full access?"}},
    {"vo": "If you use the built-in Accountant user type, functionally yes, and QuickBooks Online doesn't let you turn that down afterward. Per Intuit's own help documentation, an accountant added this way can view, add, edit, and delete transactions, and gets professional-grade tools regular users don't: undoing a whole bank reconciliation, reclassifying batches of transactions, writing off bills in bulk.", "scene": "define",
     "c": {"eyebrow": "It's near-admin, not a bookkeeper role", "term": "The Accountant user type", "body": "View, add, edit, delete transactions. Undo reconciliations. Reclassify in bulk. Write off bills."}},
    {"vo": "And the part that actually surprises most owners: Intuit's own QuickBooks Community says plainly that once someone is added as an accountant user, there's no option to adjust their access rights, because they're already set up as an admin. The only real workaround is to skip the Accountant role entirely and add the person as a Standard user instead.", "scene": "checklist",
     "c": {"title": "What the Accountant role actually is", "items": ["View, add, edit, delete every transaction", "Undo whole reconciliations, reclassify in bulk", "No dial to turn any of that down, per Intuit's own Community", "The only fix is not using this role at all"]}},

    # ---------- CH2 — why it's cheap and tempting ----------
    {"vo": "So if it's near-admin, why do so many shops still use it?", "scene": "chapter", "c": {"num": "02", "title": "Why the risky option is also the easy one"}},
    {"vo": "Because it's free, and it's fast. Per Intuit's own documentation, accountant users don't count toward a plan's paid, billed user limit, and QuickBooks Online allows up to two on Simple Start and up to three on Advanced. That makes it the cheapest way to add a bookkeeper, which is exactly why so many contractors do it, without realizing the role has no built-in ceiling once it's granted.", "scene": "stat",
     "c": {"value": "0 seats used", "label": "Accountant users don't count against a plan's paid user limit, per Intuit's own docs", "source": "QuickBooks Online accountant-access documentation"}},

    # ---------- CH3 — the real narrow path ----------
    {"vo": "So is there an actual narrow, controllable role inside QuickBooks Online, or is it Accountant-or-nothing?", "scene": "chapter", "c": {"num": "03", "title": "The real narrow path: Standard user"}},
    {"vo": "There's a real one, it's just not the default anyone reaches for. QuickBooks Online's own user roles documentation lists four options beyond Accountant: Company Admin, Standard user, Reports only, and Time tracking only. Standard user is the one built for a bookkeeper: it can be set to All Access, All Access except payroll, or Limited, and Limited breaks into five toggleable categories, Sales and Customers, Purchases and Vendors, Checking and Credit Cards, Payroll, and Sensitive Accounting Activities.", "scene": "process",
     "c": {"title": "QuickBooks Online's real role options", "steps": ["Company Admin — full control", "Standard user — All Access, except payroll, or Limited", "Reports only — free, no transaction access, no payroll reports", "Time tracking only — narrowest role"]}},
    {"vo": "Reports only is worth calling out on its own. It shows every report except payroll and contact-info reports, with zero access to the underlying transactions, and it's a free, non-billable role that doesn't count against the plan's user limit either. That fits a CPA reviewing a monthly profit and loss and nothing else. It does not fit a bookkeeper who needs to categorize transactions or reconcile a bank feed.", "scene": "define",
     "c": {"eyebrow": "The role most owners skip past", "term": "Reports only", "body": "Free, no billed seat, no transaction access. Right for a reviewing CPA — wrong for a working bookkeeper."}},

    # ---------- CH4 — Advanced tier ----------
    {"vo": "If you want fully custom, granular permissions, what does that actually cost?", "scene": "chapter", "c": {"num": "04", "title": "What granular control actually costs"}},
    {"vo": "QuickBooks Online's own documentation on custom roles states Plus offers only the preset roles, while Advanced adds true custom roles: View, Create, Edit, or Delete control across banking, payroll, reports, budgets, and inventory individually. Per current third-party pricing trackers, Advanced costs meaningfully more each month than Plus following the August 2026 price increase, and includes up to twenty five users. Plus, the tier most one-to-ten-person contractor shops actually run, tops out at five users and doesn't offer that granularity at all.", "scene": "stat",
     "c": {"value": "25 users", "label": "QuickBooks Online Advanced's user cap — the only tier with per-category custom roles, and the priciest, per current pricing trackers post Aug 2026 increase", "source": "Third-party QuickBooks Online pricing trackers"}},

    # ---------- CH5 — revoking access ----------
    {"vo": "If that relationship ends, how fast can you actually cut off a bookkeeper's QuickBooks access?", "scene": "chapter", "c": {"num": "05", "title": "Cutting off access when it ends"}},
    {"vo": "Immediately, on both role types, per Intuit's own help article on removing an accountant user. A Company Admin goes to Settings, Manage users, the Accounting Firms tab, finds the accountant, and selects Delete twice, and access is gone as soon as it's confirmed. One documented catch: accountants can't remove other accountants or themselves from that screen. Only a Primary Admin can pull that trigger, so make sure the owner, not the bookkeeper, holds that login.", "scene": "checklist",
     "c": {"title": "Revoking QuickBooks access", "items": ["Settings → Manage users → Accounting Firms tab", "Find the accountant, select Delete twice", "Access ends the moment it's confirmed", "Only a Primary Admin can do it — protect that login"]}},

    # ---------- CH6 — ServiceTitan's Accounting role ----------
    {"vo": "Now switch platforms. Does ServiceTitan even have a role built for a bookkeeper?", "scene": "chapter", "c": {"num": "06", "title": "Does ServiceTitan have a bookkeeper role?"}},
    {"vo": "Yes, it's called Accounting, one of eight roles ServiceTitan ships by default: Admin, Dispatch, Accounting, Field Managers, Technicians, Sales Managers, CSRs, and General Office, per ServiceTitan's own documentation. That same documentation says the Accounting role can perform all major accounting functions, but explicitly cannot view or edit technician payroll settings, narrower out of the box than QuickBooks Online's all-access Accountant user.", "scene": "define",
     "c": {"eyebrow": "Narrower than QuickBooks by default", "term": "ServiceTitan's Accounting role", "body": "Full accounting functions, yes. Technician payroll settings — locked out, per ServiceTitan's own docs."}},

    # ---------- CH7 — the pricebook catch ----------
    {"vo": "So ServiceTitan's default is safer than QuickBooks's. Is there a catch hiding in that same default?", "scene": "chapter", "c": {"num": "07", "title": "The catch most shops miss"}},
    {"vo": "Yes, and it cuts the other way. Per ServiceTitan's own permissions documentation, Edit service, Edit material, and Edit equipment, the exact permissions that let someone change your pricebook, are all on by default for Dispatch, Accounting, Field Manager, Sales Manager, and Admin alike. A bookkeeper sitting on the default Accounting role can, right now, change what your services cost. Turning that off takes an admin going into Settings, People, Role Permissions and manually deselecting it.", "scene": "checklist",
     "c": {"title": "What the default Accounting role can touch", "items": ["View/edit burden rate — on by default, for job-margin math", "Payroll tab on technician records — off by default", "Edit service, material, equipment pricing — ON by default", "Someone has to manually turn pricebook editing off"]}},

    # ---------- CH8 — burden rate nuance ----------
    {"vo": "What about labor cost — can a bookkeeper see burden rate without seeing a tech's actual pay?", "scene": "chapter", "c": {"num": "08", "title": "Burden rate vs. actual pay rate"}},
    {"vo": "Yes, and ServiceTitan's own permissions documentation draws that line cleanly. View or update payroll tab on technician edit is on by default only for Admin, so without it a technician's payroll tab stays greyed out entirely. A separate, narrower permission, View or edit burden rate, is on by default for Accounting. That's the split: a bookkeeper sees labor cost for job-margin math, without seeing that specific technician's actual pay rate or commission.", "scene": "define",
     "c": {"eyebrow": "One permission most shops never notice", "term": "Burden rate, not pay rate", "body": "Job-margin math stays visible. The technician's actual paycheck stays locked, unless Admin turns it on."}},

    # ---------- CH9 — exports ----------
    {"vo": "Can a ServiceTitan bookkeeper export your full customer list to Excel?", "scene": "chapter", "c": {"num": "09", "title": "Can a bookkeeper export your customer list?"}},
    {"vo": "Not on the default role, no. Per ServiceTitan's own employee-permissions documentation, Allow exporting search results, the permission that lets someone pull your customer list to Excel or CSV, is enabled only for Admin by default. A bookkeeper on Accounting can't export that list unless an admin deliberately grants it, the reverse of the pricebook problem: exports ship locked down, pricing ships open.", "scene": "stat",
     "c": {"value": "Admin-only", "label": "Customer-list export is locked by default; pricebook editing is open by default — the opposite risk profile", "source": "ServiceTitan's own employee-permissions documentation"}},

    # ---------- CH10 — no shared layer ----------
    {"vo": "Can you build one clean, read-only bookkeeper view across both systems at once, with a single setting?", "scene": "chapter", "c": {"num": "10", "title": "One setting for both systems?"}},
    {"vo": "No, and neither vendor claims otherwise. Each platform is genuinely configurable on its own side, QuickBooks Online through a Standard user role or an Advanced custom role, ServiceTitan through the role permission toggles at Settings, People, Role Permissions. But neither vendor's own documentation describes a shared or synced access layer between the two. Locking down QuickBooks doesn't touch ServiceTitan's pricebook permission, and locking down ServiceTitan doesn't touch what your Accountant user can undo in QuickBooks.", "scene": "checklist",
     "c": {"title": "What doesn't exist, per either vendor's own docs", "items": ["No shared login or synced permission layer", "QuickBooks changes don't touch ServiceTitan", "ServiceTitan changes don't touch QuickBooks", "A contractor configures both, separately, and keeps both current"]}},

    # ---------- CH11 — spouse example ----------
    {"vo": "Does it matter if the person getting access is your spouse instead of an outside bookkeeper?", "scene": "chapter", "c": {"num": "11", "title": "Does a spouse change the calculus?"}},
    {"vo": "Not to either platform's permission engine, no. This example is illustrative, built to show the mechanism, not a client result. A roofing owner adds his wife as a QuickBooks Online Accountant user so she can enter deposits on Sunday nights, and as a ServiceTitan Admin so she can pull job reports without asking him for a login. Both choices work immediately. Neither is the role either platform actually built for that job.", "scene": "stat",
     "c": {"value": "2 admin logins", "label": "One illustrative shop: a spouse handed near-admin QuickBooks access and full ServiceTitan Admin, for reports and Sunday-night deposits", "source": "Illustrative walkthrough, not a client result"}},
    {"vo": "A Standard user with Limited access in QuickBooks, and an Accounting role with pricebook editing turned off in ServiceTitan, would have covered the exact same daily work, entering deposits, pulling job reports, without the admin-level blast radius sitting on either side the whole time.", "scene": "define",
     "c": {"eyebrow": "Same daily work, a fraction of the risk", "term": "What should have been granted instead", "body": "QuickBooks Standard + Limited categories. ServiceTitan Accounting, pricebook editing off."}},

    # ---------- CH12 — the two failure patterns ----------
    {"vo": "So what do most contractors actually do instead of building this properly?", "scene": "chapter", "c": {"num": "12", "title": "The two patterns most shops fall into"}},
    {"vo": "Based on how both platforms' defaults behave, shops tend to land on one of two patterns, and neither is really a solution. The first is over-granting: Accountant user plus ServiceTitan Admin, because it's the fast path and nobody has an afternoon to map role permissions. The second is under-granting: keeping the bookkeeper out of both systems entirely and exporting PDFs by hand, which sidesteps the access question but recreates the exact manual re-keying that turns job-cost numbers stale.", "scene": "checklist",
     "c": {"title": "Two patterns, both broken", "items": ["Over-granting — Accountant user + full Admin, for speed", "Under-granting — locked out, exporting PDFs by hand instead", "Over-granting exposes the pricebook and every transaction", "Under-granting recreates stale, re-keyed numbers"]}},

    # ---------- CH13 — the fix ----------
    {"vo": "So what actually closes this gap for a shop running ServiceTitan and QuickBooks together?", "scene": "chapter", "c": {"num": "13", "title": "What actually closes the gap"}},
    {"vo": "A permission audit that walks both systems together, in the same sitting: QuickBooks Online set to a Standard user with the right Limited categories chosen deliberately, not Accountant by default; ServiceTitan's Accounting role with pricebook editing manually turned off, in Settings, People, Role Permissions, before the invite goes out, not after. Neither platform does this pairing for you. Someone has to walk both, on purpose, and then keep checking both every time a bookkeeper's role changes.", "scene": "process",
     "c": {"title": "The audit, walked once, on purpose", "steps": ["QuickBooks: Standard user, Limited categories chosen deliberately", "ServiceTitan: Accounting role, pricebook editing turned off", "Do both before the invite goes out, not after", "Recheck both whenever the relationship or role changes"]}},

    # ---------- CH14 — where Top Builder AI fits ----------
    {"vo": "Where does Top Builder AI fit into this, if it doesn't replace either platform's login screen?", "scene": "chapter", "c": {"num": "14", "title": "Where Top Builder AI actually fits"}},
    {"vo": "It doesn't touch either vendor's permission system, and it doesn't need to. The Financial agent reads the same job-cost and accounting data your bookkeeper already sees, on whatever role you've actually configured for her, and narrates margin and cash-position findings back to you without ever needing its own admin login into either platform. It's built on top of the access boundary you set, not around it.", "scene": "define",
     "c": {"eyebrow": "Sits on top of your access boundary", "term": "Read-only against your real roles", "body": "No separate admin login. No new permission layer to audit. It works within whatever roles you've already set."}},
    {"vo": "No edited records — your QuickBooks and ServiceTitan data stays exactly as your team and your bookkeeper enter it. No invented numbers — every figure traces back to a real transaction in one of the two systems. No blind self-serve signup — it's configured against your actual roles and your actual books, not a demo account.", "scene": "checklist",
     "c": {"title": "What this is, and isn't", "items": ["No edited records — your books stay as entered", "No invented numbers — every figure traces to a real transaction", "Not a blind self-serve signup — configured on your real access", "Doesn't add a third permission system to audit"]}},

    # ---------- CTA ----------
    {"vo": "So here's the fastest way to check this yourself. Open QuickBooks Online right now and look at Manage users. If your bookkeeper shows up as an Accountant, she has near-admin access with no dial to turn down, full stop. Then open ServiceTitan's Settings, People, Role Permissions, and check whether Edit service is still switched on for the Accounting role. If it is, she can change your pricebook today, whether anyone meant to grant that or not.", "scene": "cta",
     "c": {"eyebrow": "Check both roles before the next invite goes out", "title": "What Access Did You Actually Grant?", "sub": "Two logins, two default settings — most owners have never checked either", "url": "topbuilderai.com"}},
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
