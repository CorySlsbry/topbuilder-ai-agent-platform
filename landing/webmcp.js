/*
 * WebMCP marketing manifest for topbuilderai.com (publish-as-we-go standing rule).
 *
 * Declares read-only + lead-capture tools via the WebMCP standard so browser AI agents
 * (e.g. Gemini in Chrome) can ACT on this page instead of scraping the DOM. Every tool here
 * is feature-detected and a graceful no-op in browsers without WebMCP — the page is unaffected.
 *
 * Security posture: all content returned is PUBLIC marketing data. `check_pricing` and
 * `list_agents` are read-only (readOnlyHint:true). `book_demo` performs NO unauthenticated
 * write — it only returns the public booking link. A WebMCP tool is a client-side declaration,
 * so any real action remains gated server-side (see enterprise-security-audit). Nothing here
 * touches customer data, auth, or the application API.
 */
(function () {
  "use strict";

  // Feature-detect the WebMCP surface. Absent it (most browsers today), do nothing.
  if (typeof document === "undefined" || !document.modelContext || typeof document.modelContext.registerTool !== "function") {
    return;
  }

  var BOOKING = "https://book.topbuilderai.com";
  var SUPPORT = "support@topbuilderai.com";

  // text-content helper for a tool result.
  function say(text) {
    return { content: [{ type: "text", text: text }] };
  }

  // Register defensively — one bad tool must never break the others or the page.
  function register(tool) {
    try {
      document.modelContext.registerTool(tool);
    } catch (e) {
      /* no-op: a registration failure is non-fatal for a marketing manifest */
    }
  }

  register({
    name: "check_pricing",
    description:
      "Get Top Builder AI pricing: a one-time install fee (waived this quarter) plus a monthly plan that scales " +
      "with how many people use the system.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true },
    execute: function () {
      return say(
        "One one-time install plus a monthly that scales with how many people use the system. Every " +
        "tier includes all eight self-learning agents; the monthly is billed off your connected field " +
        "platform (ServiceTitan, Procore, or Buildertrend) and QuickBooks employee count, not self-reported seats.\n" +
        "- Up to 25 people (Operator): $3,000/mo.\n" +
        "- 26 to 75 people (Back-Office Command): $4,500/mo.\n" +
        "- 76 to 125 people (Back-Office Command): $6,000/mo.\n" +
        "- 126 to 250 people (Command Suite): $8,000/mo plus a managed-operations retainer.\n" +
        "- Above 250 people: custom.\n" +
        "The one-time install is $0 this quarter (normally $8,000), or pay the install and keep the " +
        "monthly flexible. Your rate stays locked for as long as you stay, and every tier carries the " +
        "30-day board-ready-or-free guarantee. Book a fit call to confirm your tier: " + BOOKING
      );
    }
  });

  register({
    name: "list_agents",
    description:
      "List the AI agents Top Builder AI provides and what each one does. Booking and Inventory are " +
      "ServiceTitan-only today; the other six (Workforce, Routing, Documents, Financial, Collections, " +
      "Pricebook) work across ServiceTitan, Procore and Buildertrend.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true },
    execute: function () {
      return say(
        "Eight self-learning AI agents that get smarter every week:\n" +
        "1. Booking - 24/7 inbound call and message handling that qualifies, slots, and values every call incl. after-hours, tuned to your shop.\n" +
        "2. Routing / Dispatch - drive-time-optimized assignment that also weighs margin, parts and overtime with P1/P2/P3 triage.\n" +
        "3. Financial - projects 30/60/90-day cash and flags margin leakage the day it appears, reconciled to your actual QuickBooks general ledger (the 'Money' back office).\n" +
        "4. Inventory - reorders, shrinkage, unbilled materials and partial-consumable (spool/coil) cost proration (the 'Materials' back office).\n" +
        "5. Workforce - staffing + avoidable-overtime forecasting, payroll overtime, and a rolling capacity moving target (the 'People' back office).\n" +
        "6. Documents - classify, route, extract and file every document, incl. AP-from-emailed-bill and warranty registration (the 'Paperwork' back office).\n" +
        "7. Collections - works the A/R aging worklist 24/7 with dunning email/SMS/call drafts and promise-to-pay tracking, the follow-up ServiceTitan leaves manual (the 'A/R' back office).\n" +
        "8. Pricebook - keeps materials costs current as your vendor costs rise and re-prices every item under the sold-hour model, human-approved (the 'Pricebook' back office).\n" +
        "All are multi-tenant, audited, and advisory-by-default behind a human-approved action gate. " +
        "We plug in alongside ServiceTitan and run the back-office work it leaves manual or leaves to " +
        "QuickBooks, tuned to your specific shop. We never touch your system of record.\n" +
        "Platform scope: Booking and Inventory are ServiceTitan-only today. The other six (Workforce, " +
        "Routing, Documents, Financial, Collections, Pricebook) work across ServiceTitan, Procore and " +
        "Buildertrend, with Pricebook served via vendor price-file upload; accounting connections " +
        "activate per customer."
      );
    }
  });

  register({
    name: "list_starter_offers",
    description:
      "List Top Builder AI's paid starter offers: three small, fixed-price, done-for-you engagements " +
      "(Margin Leakage X-Ray $97, A/R Collections Sprint $97, CEO Scorecard $27 for 14 days) that let a " +
      "contractor buy a result before the full platform install. Every dollar credits toward any install.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true },
    execute: function () {
      return say(
        "Three paid starter offers, each done for you (not self-serve), each crediting dollar-for-dollar " +
        "toward any Top Builder AI install:\n" +
        "1. Margin Leakage X-Ray - $97 - https://topbuilderai.com/margin-leakage-xray.html\n" +
        "   Connect QuickBooks read-only or upload a P&L + job list; a board-ready report shows exactly " +
        "where the business leaks margin (unbilled materials, job-cost drift, aging A/R) with the dollar " +
        "figure per month, within 48 hours of the data handoff. Guarantee: at least $10,000/year in " +
        "leakage found or it is free.\n" +
        "2. A/R Collections Sprint - $97 - https://topbuilderai.com/ar-collections-sprint.html\n" +
        "   Send an A/R aging report (QuickBooks or ServiceTitan); within 24 hours you get a ranked chase " +
        "queue (who to call first and why), ready-to-send collection emails, and call scripts " +
        "personalized per overdue customer.\n" +
        "3. CEO Scorecard - $27 for 14 days - https://topbuilderai.com/ceo-scorecard.html\n" +
        "   14 days inside the actual Top Builder AI platform with the contractor's own data loaded, set " +
        "up for them: the department scorecard, KPI trends with the seasonal forecast band, and the " +
        "executive view. Live within 2 business days of the handoff call; no auto-renewal on day 15.\n" +
        "Each purchase is followed by a 15-minute data handoff call booked at " + BOOKING + "."
      );
    }
  });

  register({
    name: "book_demo",
    description:
      "Start booking a demo / discovery call with Top Builder AI. Returns the public booking link " +
      "(no account or write is performed here).",
    inputSchema: {
      type: "object",
      properties: {
        email: { type: "string", description: "Your email (optional), pre-fills the booking form." }
      },
      additionalProperties: false
    },
    // Not read-only (it's the lead-capture entry point) but performs no server write itself.
    execute: function (args) {
      var email = args && typeof args.email === "string" ? args.email.trim() : "";
      var url = email ? BOOKING + "?email=" + encodeURIComponent(email) : BOOKING;
      return say(
        "Book your fit call here: " + url +
        "\nPrefer email? Reach the founder at " + SUPPORT + "."
      );
    }
  });
})();
