# Wiring EmailView + SeoView into `app/page.tsx`

Four edits, all inside `app/page.tsx`. **No changes to `lib/api.ts` or `lib/types.ts`** — both
views are self-loading (they take `token` and fetch their own data, exactly like
`FrontDeskView` / `LearningView`), so they need **no `SECTION_AGENT` entry, no `RUN_QUERY`
entry, no `AgentName` extension, and no `DataMap` change**. Each view ships its own
"Run briefing" / "Run weekly analysis" button (the header Run button stays hidden for these
sections because `SECTION_AGENT[section]` is `undefined` — same as Front Desk/Learning).

## 1. Imports (top of file)

Insert alphabetically among the existing component imports:

```diff
 import AgentControls from "@/components/AgentControls";
 import BookingView from "@/components/BookingView";
 import DispatchView from "@/components/DispatchView";
 import DocumentsView from "@/components/DocumentsView";
+import EmailView from "@/components/EmailView";
 import FinancialView from "@/components/FinancialView";
 import FrontDeskView from "@/components/FrontDeskView";
 import InventoryView from "@/components/InventoryView";
 import LearningView from "@/components/LearningView";
+import SeoView from "@/components/SeoView";
 import { EmptyState, Spark, Spinner } from "@/components/ui";
 import WorkforceView from "@/components/WorkforceView";
```

## 2. The `Section` union type

```diff
 type Section =
   | "dispatch" | "frontdesk" | "documents" | "controls" | "learning"
-  | "workforce" | "financial" | "inventory" | "booking";
+  | "workforce" | "financial" | "inventory" | "booking" | "email" | "seo";
```

(`SECTION_AGENT` is `Partial<Record<Section, AgentName>>`, so it compiles unchanged with the
two new keys absent — that absence is what routes these sections down the self-loading path.)

## 3. Sidebar entries — `NAV`, "Agents" group, after Booking

```diff
   {
     group: "Agents",
     items: [
       { key: "workforce", label: "Workforce", blurb: "Forecast understaffing and avoidable overtime." },
       { key: "financial", label: "Financial", blurb: "Project cash and surface margin leakage." },
       { key: "inventory", label: "Inventory", blurb: "Reorders, shrinkage, unbilled materials, vendor savings." },
       { key: "booking", label: "Booking", blurb: "Qualify, slot, and value every inbound call 24/7." },
+      { key: "email", label: "Email", blurb: "Daily inbox briefing, reply drafts, cleanup, and workflow watch — nothing sends without approval." },
+      { key: "seo", label: "SEO & Content", blurb: "Competitor gaps, GEO scorecard, blog queue, and comment drafts — you approve before anything posts." },
     ],
   },
 ];
```

## 4. View switch — add the branches WITH the self-loading group

The two new branches **must** sit alongside `frontdesk`/`controls`/`learning`, i.e. **before**
the `busy && !current` / `!current` checks. If placed after, they would never render: with no
`SECTION_AGENT` entry, `current` is always `null` for these sections and they'd be swallowed
by the `EmptyState` branch.

```diff
           {section === "frontdesk" ? (
             <FrontDeskView token={token} />
           ) : section === "controls" ? (
             <AgentControls token={token} />
           ) : section === "learning" ? (
             <LearningView token={token} />
+          ) : section === "email" ? (
+            <EmailView token={token} />
+          ) : section === "seo" ? (
+            <SeoView token={token} />
           ) : busy && !current ? (
             <div className="panel grid place-items-center px-6 py-20 text-zinc-500">
               <Spinner />
               <span className="mt-3 text-sm">Loading {meta.label.toLowerCase()}…</span>
             </div>
```

That's everything. The `meta` lookup (`NAV.flatMap((g) => g.items).find(...)`) picks up the new
entries automatically, and the run-footer (`current && agent && <footer …>`) correctly stays
hidden for these sections.

## Endpoints the views call (backend contract)

- `EmailView`: `GET /v1/agents/email/runs/latest` on mount (404 → empty state),
  `POST /v1/agents/email/runs` from the "Run briefing" button.
- `SeoView`: `GET /v1/agents/seo/runs/latest` on mount (404 → empty state),
  `POST /v1/agents/seo/runs` from the "Run weekly analysis" button.
- Auth: `Authorization: Bearer <dev-token>` on every call; base URL =
  `NEXT_PUBLIC_API_BASE_URL` (trailing slash stripped) falling back to `http://localhost:8000`
  — byte-for-byte the `lib/api.ts` conventions, replicated locally inside each view file.
