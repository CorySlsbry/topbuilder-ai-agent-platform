"""Canyon Ridge Mechanical — the seeded 38-person demo roster (PURE data, no DB).

Single source of truth for the Alex demo org: 7 departments, 38 people, manager edges, and a
per-person ai_context written AS INSTRUCTIONS TO THE AI (how to talk to / work for this person).
Seeded on first read by repositories/org.ensure_seeded (the comms/tasks seed-on-read pattern).
IDs are deterministic (uuid5) so re-seeding is idempotent and links survive re-deploys.
"""
from __future__ import annotations

import uuid

from app.org.permissions import DEPARTMENTS

CANYONRIDGE_TENANT_ID = "33333333-3333-3333-3333-333333333333"


def person_id(slug: str) -> uuid.UUID:
    """Deterministic person id — stable across seeds (uuid5 of the roster slug)."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"tba:canyonridge:person:{slug}")


def dept_id(key: str) -> uuid.UUID:
    """Deterministic department id — stable across seeds (uuid5 of the department key)."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"tba:canyonridge:dept:{key}")


def _p(
    slug: str,
    full_name: str,
    title: str,
    department: str,
    role_tier: str,
    manager_slug: str | None,
    ai_context: str,
    sort: int,
) -> dict:
    return {
        "slug": slug,
        "full_name": full_name,
        "title": title,
        "department": department,
        "role_tier": role_tier,
        "manager_slug": manager_slug,
        "ai_context": ai_context,
        "sort": sort,
    }


PEOPLE: list[dict] = [
    # --- leadership (3) ---------------------------------------------------------------------
    _p("alex", "Alex", "Owner / CEO", "leadership", "owner", None,
       "Owner who also runs the numbers — a bookkeeping/CPA-channel partner fluent in GAAP. "
       "Lead with board-level summaries: dollar impact first, then the action. GAAP-aware "
       "language is fine; never hedge a figure he can reconcile himself.", 1),
    _p("marcus-reed", "Marcus Reed", "General Manager", "leadership", "exec", "alex",
       "Runs day-to-day P&L across departments. Give him week-over-week deltas and which "
       "department owns each number; flag anything that needs a same-day decision.", 2),
    _p("elena-vasquez", "Elena Vasquez", "Operations Manager", "leadership", "exec", "alex",
       "Owns field, dispatch, and warehouse operations. Lead with capacity and schedule risk; "
       "she wants the operational fix, not the financial framing.", 3),
    # --- front_office (5) -------------------------------------------------------------------
    _p("tanya-brooks", "Tanya Brooks", "Office Manager", "front_office", "manager", "marcus-reed",
       "Runs the front office and the CSR team. Summarize the booking queue and unanswered "
       "communications first; she approves agent-proposed bookings, so always show the value of "
       "each call.", 1),
    _p("april-nguyen", "April Nguyen", "CSR — Lead", "front_office", "ic", "tanya-brooks",
       "Senior CSR who trains the others. Give her call-handling specifics — what was qualified, "
       "what was screened out and why — so she can coach the team.", 2),
    _p("joelle-king", "Joelle King", "CSR", "front_office", "ic", "tanya-brooks",
       "Front-line CSR on inbound calls. Keep instructions short and scripted: who to call back, "
       "what to say, which slot to offer.", 3),
    _p("brandon-pierce", "Brandon Pierce", "CSR", "front_office", "ic", "tanya-brooks",
       "CSR who handles email and web inquiries. Surface follow-ups in priority order with a "
       "ready-to-send draft for each.", 4),
    _p("sofia-marin", "Sofia Marin", "CSR", "front_office", "ic", "tanya-brooks",
       "Newest CSR, still learning the trades. Spell out the trade and job type on every booking; "
       "avoid abbreviations she may not know yet.", 5),
    # --- dispatch (3) -----------------------------------------------------------------------
    _p("ray-delgado", "Ray Delgado", "Dispatch Manager", "dispatch", "manager", "elena-vasquez",
       "Owns the daily board. Lead with drive-time saved and unassigned jobs; he wants the "
       "suggested assignment plan first and the reasoning only if he asks.", 1),
    _p("nikki-tran", "Nikki Tran", "Dispatcher", "dispatch", "ic", "ray-delgado",
       "Works the morning board. Give her tech-by-tech route changes in order, with the customer "
       "callback number on every reassignment.", 2),
    _p("omar-haddad", "Omar Haddad", "Dispatcher", "dispatch", "ic", "ray-delgado",
       "Covers afternoons and emergencies. Flag same-day capacity risks early and always name the "
       "nearest qualified tech for an urgent call.", 3),
    # --- field (18) -------------------------------------------------------------------------
    _p("cole-barrett", "Cole Barrett", "Field Supervisor", "field", "manager", "elena-vasquez",
       "Supervises all 17 field techs across three trades. Lead with crew utilization and "
       "overtime risk by trade; he decides who works Saturdays.", 1),
    _p("jt-ramsey", "J.T. Ramsey", "HVAC Lead Technician", "field", "ic", "cole-barrett",
       "Senior HVAC lead who mentors the install crews. Give him job-level technical detail and "
       "equipment specs; he double-checks every quote over $5k.", 2),
    _p("sam-okafor", "Sam Okafor", "HVAC Service Technician", "field", "ic", "cole-barrett",
       "Service tech on maintenance agreements. Keep his schedule tight and geographic; he prefers "
       "his day grouped by neighborhood.", 3),
    _p("petra-iliev", "Petra Iliev", "HVAC Install Technician", "field", "ic", "cole-barrett",
       "Install tech on multi-day change-outs. Tell her the materials staged for each job before "
       "she rolls; missing parts are her biggest time loss.", 4),
    _p("dev-patel", "Dev Patel", "HVAC Service Technician", "field", "ic", "cole-barrett",
       "Diagnostics specialist — gets the weird no-cool calls. Attach full service history to "
       "every job you route him.", 5),
    _p("marcus-webb", "Marcus Webb", "HVAC Install Technician", "field", "ic", "cole-barrett",
       "Install tech, strongest on rooftop units. Note crane or two-person requirements on his "
       "jobs explicitly.", 6),
    _p("lily-chen", "Lily Chen", "HVAC Service Technician", "field", "ic", "cole-barrett",
       "Service tech who sells the most memberships. Surface membership-eligible customers on her "
       "route each morning.", 7),
    _p("hank-sorensen", "Hank Sorensen", "HVAC Service Technician", "field", "ic", "cole-barrett",
       "20-year veteran, mentors apprentices on ride-alongs. Keep his instructions brief — job, "
       "address, contact — he'll handle the rest.", 8),
    _p("reuben-ortiz", "Reuben Ortiz", "HVAC Install Technician", "field", "ic", "cole-barrett",
       "Newer install tech, fast but still building accuracy. Include the install checklist on "
       "every job packet you send him.", 9),
    _p("gina-russo", "Gina Russo", "Plumbing Lead", "field", "ic", "cole-barrett",
       "Runs the plumbing crew day-to-day. Give her the crew's full-day view, not single jobs, "
       "and flag any permit-required work first.", 10),
    _p("felix-mora", "Felix Mora", "Plumber", "field", "ic", "cole-barrett",
       "Journeyman on service calls and repipes. Note water-shutoff and access details on every "
       "ticket; surprises on site cost him hours.", 11),
    _p("tommy-vu", "Tommy Vu", "Plumber", "field", "ic", "cole-barrett",
       "Drain and sewer specialist with the camera rig. Route all sewer-scope jobs to him and "
       "attach prior scope footage when it exists.", 12),
    _p("jared-blake", "Jared Blake", "Apprentice Plumber", "field", "ic", "cole-barrett",
       "Second-year apprentice, rides with Felix or Gina. Never schedule him solo; pair every "
       "assignment with a journeyman.", 13),
    _p("anya-petrova", "Anya Petrova", "Apprentice Plumber", "field", "ic", "cole-barrett",
       "First-year apprentice tracking licensing hours. Log the task type on each job so her "
       "hours are creditable.", 14),
    _p("dom-castellano", "Dom Castellano", "Electrical Lead", "field", "ic", "cole-barrett",
       "Leads the electrical crew; master license holder. He signs off all panel work — route "
       "anything over 100A through him.", 15),
    _p("kara-lindqvist", "Kara Lindqvist", "Electrician", "field", "ic", "cole-barrett",
       "Journeyman strongest on EV chargers and generator installs. Include load-calculation "
       "inputs with every install job.", 16),
    _p("miguel-santos", "Miguel Santos", "Electrician", "field", "ic", "cole-barrett",
       "Service electrician on troubleshooting calls. Give him the customer's reported symptoms "
       "verbatim — he triages from the homeowner's words.", 17),
    _p("theo-brandt", "Theo Brandt", "Apprentice Electrician", "field", "ic", "cole-barrett",
       "Apprentice under Dom. Keep him on prep and pull work; never assign him hot work or final "
       "connections.", 18),
    # --- sales (3) --------------------------------------------------------------------------
    _p("dana-royce", "Dana Royce", "Sales Manager", "sales", "manager", "marcus-reed",
       "Owns the sales pipeline and close rate. Lead with unsold estimates over $3k and aging "
       "follow-ups; she wants the call list ranked by deal size.", 1),
    _p("wes-calloway", "Wes Calloway", "Comfort Advisor", "sales", "ic", "dana-royce",
       "In-home advisor on replacement quotes. Prep him before each visit: equipment age, service "
       "history, and any financing the customer mentioned.", 2),
    _p("ingrid-hale", "Ingrid Hale", "Comfort Advisor", "sales", "ic", "dana-royce",
       "Advisor focused on IAQ and add-ons. Flag duct, filtration, and humidity findings from "
       "service visits so she can follow up with a tailored offer.", 3),
    # --- finance (3) ------------------------------------------------------------------------
    _p("priya-shah", "Priya Shah", "Controller", "finance", "manager", "marcus-reed",
       "Controller. Numbers must reconcile to QuickBooks before she sees them; lead with cash "
       "position and margin variance, and cite the source for every figure.", 1),
    _p("rosa-delgado", "Rosa Delgado", "Bookkeeper", "finance", "ic", "priya-shah",
       "Handles AP/AR and job costing. Give her exception lists — unbilled materials, unmatched "
       "invoices — with the job number on every line.", 2),
    _p("evan-marsh", "Evan Marsh", "Payroll Administrator", "finance", "ic", "priya-shah",
       "Runs payroll Mondays. Deliver timesheet exceptions and overtime flags by Friday close, "
       "grouped by tech, ready for approval.", 3),
    # --- warehouse (3) ----------------------------------------------------------------------
    _p("gus-romero", "Gus Romero", "Warehouse Manager", "warehouse", "manager", "elena-vasquez",
       "Owns stock levels and vendor orders. Lead with reorder alerts and shrinkage variance; he "
       "wants vendor price comparisons before any PO over $1k.", 1),
    _p("pete-kowalski", "Pete Kowalski", "Inventory Clerk", "warehouse", "ic", "gus-romero",
       "Handles receiving and truck restock. Give him pick lists by truck, in bin order, the "
       "night before.", 2),
    _p("mae-johnson", "Mae Johnson", "Inventory Clerk", "warehouse", "ic", "gus-romero",
       "Does cycle counts and returns. Flag count discrepancies the same day with the last three "
       "transactions on the item.", 3),
]

SEED_TENANTS: dict[str, dict] = {
    CANYONRIDGE_TENANT_ID: {
        "company_name": "Canyon Ridge Mechanical",
        "provider": "servicetitan",
        "departments": DEPARTMENTS,
        "people": PEOPLE,
    },
}
