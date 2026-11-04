"use client";

import { useEffect, useRef, useState } from "react";

import AdsCrmView from "@/components/ads/AdsCrmView";
import AgentControls from "@/components/AgentControls";
import AssistantDock from "@/components/AssistantDock";
import AuthGate from "@/components/AuthGate";
import BookingView from "@/components/BookingView";
import BusinessPlanView from "@/components/BusinessPlanView";
import CapacityView from "@/components/CapacityView";
import CollectionsView from "@/components/CollectionsView";
import DispatchBoardView from "@/components/DispatchBoardView";
import DispatchView from "@/components/DispatchView";
import DocumentsView from "@/components/DocumentsView";
import EmailView from "@/components/EmailView";
import ExecutiveView from "@/components/ExecutiveView";
import FinancialView from "@/components/FinancialView";
import ApprovalsView from "@/components/ApprovalsView";
import FrontDeskView from "@/components/FrontDeskView";
import InventoryView from "@/components/InventoryView";
import IssuesView from "@/components/IssuesView";
import KpiTrendsView from "@/components/KpiTrendsView";
import LearningView from "@/components/LearningView";
import OrgBrainView from "@/components/OrgBrainView";
import PricebookView from "@/components/PricebookView";
import SecurityPanel from "@/components/SecurityPanel";
import SeoView from "@/components/SeoView";
import { EmptyState, Spark, Spinner } from "@/components/ui";
import ViewAsControl from "@/components/ViewAsControl";
import WorkforceView from "@/components/WorkforceView";
import {
  getAgentLatest,
  getCapacityLatest,
  getDevToken,
  getTriageLatest,
  runAgent,
  runCapacity,
  runTriage,
} from "@/lib/api";
import { getMe, type Me } from "@/lib/auth-api";
import { activeSupabase } from "@/lib/supabase";
import type {
  AgentName,
  AgentResult,
  BookingRunResult,
  CapacityRunResult,
  DocumentsRunResult,
  FinancialRunResult,
  InventoryRunResult,
  RoutingRunResult,
  SimulatedView,
  TriageRunResult,
  WorkforceRunResult,
} from "@/lib/types";

// The public demo shows ONE seeded company (apex/summit stay seeded backend-side for tests/cron,
// but only Canyon Ridge is presented).
const TENANTS = [
  { slug: "canyonridge", name: "Canyon Ridge Mechanical" },
];

type Section =
  | "organization" | "executive" | "kpitrends" | "dispatch" | "dispatchboard" | "capacity" | "frontdesk" | "collections"
  | "documents" | "pricebook" | "controls" | "learning" | "issues" | "businessplan" | "approvals"
  | "workforce" | "financial" | "inventory" | "booking" | "email" | "seo" | "adscrm";

// Sections backed by an agent run (the rest load their own data).
const SECTION_AGENT: Partial<Record<Section, AgentName>> = {
  dispatch: "routing",
  documents: "documents",
  workforce: "workforce",
  financial: "financial",
  inventory: "inventory",
  booking: "booking",
};
const RUN_QUERY: Partial<Record<AgentName, string>> = { workforce: "horizon_days=21" };

const NAV: { group: string; items: { key: Section; label: string; blurb: string }[] }[] = [
  {
    group: "Command",
    items: [
      { key: "organization", label: "Organization", blurb: "Your whole company — every person, department, and agent — and what the AI knows about each." },
      { key: "executive", label: "Executive", blurb: "Enterprise KPIs from every agent's latest run — value identified, AI coverage, and the org at a glance." },
      { key: "kpitrends", label: "KPI Trends", blurb: "Rolling-year KPI trends with 13-week and 6-month seasonal projections." },
      { key: "dispatch", label: "Dispatch", blurb: "Today's drive-time-optimized assignment plan — accept or override." },
      { key: "dispatchboard", label: "Dispatch Board", blurb: "Triage the day P1–P3 — emergencies first, each job's best skill+revenue+proximity tech, and the 3-day call board." },
      { key: "capacity", label: "Capacity", blurb: "Each tech's learned pace vs baseline, and who's heading into overtime next week — with who has the slack to absorb it." },
      { key: "frontdesk", label: "Front Desk", blurb: "Every call, text, and email in one inbox, with the booking queue and tasks." },
      { key: "approvals", label: "My Approvals", blurb: "Actions awaiting your approval — your department's queue. Approve or disapprove each." },
      { key: "collections", label: "Collections", blurb: "Work the A/R worklist — aging buckets, who owes, the next dunning step, and promise-to-pay." },
      { key: "documents", label: "Documents", blurb: "Classify, extract, and file every document to the right customer + ServiceTitan folder." },
      { key: "pricebook", label: "Pricebook", blurb: "Keep materials costs current from vendor updates and re-price every catalog item under your sold-hour model." },
      { key: "controls", label: "Agent Controls", blurb: "Set each agent's autonomy: Off, Approve, or Auto." },
      { key: "learning", label: "Learning", blurb: "Review, approve, and roll out what the agents learn — gated by an eval + canary." },
      { key: "issues", label: "Issues", blurb: "The L10 issues list (IDS) — what needs solving, owned and prioritized; add or resolve." },
      { key: "businessplan", label: "Business Plan", blurb: "Annual goals, budget-to-actual, and the trailing-12 P&L — auto-pulled, not keyed." },
    ],
  },
  {
    group: "Agents",
    items: [
      { key: "workforce", label: "Workforce", blurb: "Forecast understaffing and avoidable overtime." },
      { key: "financial", label: "Financial", blurb: "Project cash and surface margin leakage." },
      { key: "inventory", label: "Inventory", blurb: "Reorders, shrinkage, unbilled materials, vendor savings." },
      { key: "booking", label: "Booking", blurb: "Qualify, slot, and value every inbound call 24/7." },
    ],
  },
  {
    // Platform-operator tools (super-admin layer) — hidden from the customer-facing Command Center.
    // Server-side the /v1/agents/{email,seo} routes also require the admin role.
    group: "Operator",
    items: [
      { key: "email", label: "Email", blurb: "Daily inbox briefing, reply drafts, cleanup, and workflow watch — nothing sends without approval." },
      { key: "seo", label: "SEO & Content", blurb: "Competitor gaps, GEO scorecard, blog queue, and comment drafts — you approve before anything posts." },
      { key: "adscrm", label: "Ads & CRM", blurb: "Your go-to-market pipeline, Meta & Google Ads campaigns, and ad accounts — every spend action gated + approved." },
    ],
  },
];

// Canyon Ridge department palette (mirrors the /v1/org/overview colors) for the signed-in chip.
const DEPT_COLORS: Record<string, string> = {
  leadership: "#f59e0b",
  front_office: "#38bdf8",
  dispatch: "#a78bfa",
  field: "#34d399",
  sales: "#fb7185",
  finance: "#818cf8",
  warehouse: "#fb923c",
};

// Department-scoped accounts: null allowed list = unrestricted (dev tokens, executives, admins).
// The helpers take the raw allowed arrays so the same logic serves the real principal AND the
// View-As simulation (which substitutes a person's computed scope).
const sectionAllowed = (allowed: string[] | null, s: Section) => !allowed || allowed.includes(s);
const agentAllowed = (allowed: string[] | null, a: AgentName) => !allowed || allowed.includes(a);
const firstAllowedSection = (allowed: string[] | null): Section => {
  const keys = NAV.flatMap((g) => g.items.map((i) => i.key));
  return keys.find((k) => sectionAllowed(allowed, k)) ?? "organization";
};

// Department color chip (signed-in identity + View-As). Mirrors the /v1/org/overview colors.
function DeptChip({ dept }: { dept: string }) {
  const c = DEPT_COLORS[dept] ?? "#a1a1aa";
  return (
    <span
      className="inline-flex rounded-md border px-1.5 py-px text-[10px] font-medium capitalize"
      style={{ color: c, borderColor: `${c}55`, backgroundColor: `${c}1a` }}
    >
      {dept.replace(/_/g, " ")}
    </span>
  );
}

type DataMap = Record<AgentName, AgentResult | null>;
// Pricebook (like Collections) is self-loading via its own view, not the SECTION_AGENT run path; the key
// is present only to satisfy the AgentName-keyed map.
const EMPTY_DATA: DataMap = { workforce: null, financial: null, inventory: null, booking: null, routing: null, documents: null, pricebook: null };

export default function Page() {
  const [token, setToken] = useState<string | null>(null);
  const [tenant, setTenant] = useState(TENANTS[0]);
  const [section, setSection] = useState<Section>("dispatch");
  const [data, setData] = useState<DataMap>(EMPTY_DATA);
  const [loaded, setLoaded] = useState<Set<AgentName>>(new Set());
  const [pending, setPending] = useState<AgentName | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [light, setLight] = useState(false);
  // Capacity + Dispatch-board: own (non-standard) endpoints + run, self-fetched (not the SECTION_AGENT path).
  const [capacity, setCapacity] = useState<CapacityRunResult | null>(null);
  const [triage, setTriage] = useState<TriageRunResult | null>(null);
  const [customBusy, setCustomBusy] = useState(false);
  // Super-admin (platform operator) mode: unlock via ?superadmin=1 once, persisted; ?superadmin=0 clears.
  const [superAdmin, setSuperAdmin] = useState(false);
  // Real (Supabase) auth: `me` from /auth/me; null in the demo flow.
  const [me, setMe] = useState<Me | null>(null);
  const [realAuth, setRealAuth] = useState(false);
  const [securityOpen, setSecurityOpen] = useState(false);
  // View-As: presentational scoping for an UNRESTRICTED operator — the UI adopts the chosen
  // person's allowed sections/agents so an owner sees exactly what that login sees. Real users
  // are enforced server-side (require_agent_access); this never widens anyone's access.
  const [simulated, setSimulated] = useState<SimulatedView | null>(null);
  // Latest token, readable synchronously (SecurityPanel hands a fresh token + asks for a /auth/me refetch back-to-back).
  const tokenRef = useRef<string | null>(null);

  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    if (qs.has("superadmin")) {
      localStorage.setItem("tba_superadmin", qs.get("superadmin") === "0" ? "0" : "1");
    }
    setSuperAdmin(localStorage.getItem("tba_superadmin") === "1");
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("light", light);
  }, [light]);

  // Effective scope = the simulation when active, the real principal otherwise. Drives the nav
  // filter, the section auto-redirect, the agent-fetch guards, and the signed-in chip.
  const effectiveSections = simulated ? simulated.sections : me?.allowed_sections ?? null;
  const effectiveAgents = simulated ? simulated.agents : me?.allowed_agents ?? null;

  // Out-of-scope section (restricted login OR a just-activated simulation) → first allowed one.
  useEffect(() => {
    if (effectiveSections && !effectiveSections.includes(section)) {
      setSection(firstAllowedSection(effectiveSections));
    }
  }, [effectiveSections, section]);

  const agent = SECTION_AGENT[section];

  async function loadLatest(tok: string, a: AgentName) {
    setPending(a);
    setError(null);
    try {
      const res = await getAgentLatest<AgentResult>(tok, a);
      setData((d) => ({ ...d, [a]: res }));
      setLoaded((s) => new Set(s).add(a));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    } finally {
      setPending(null);
    }
  }

  // Capacity + Dispatch-board fetch their own (non-/runs) endpoints; mirror loadLatest/run for them.
  async function loadCustom(tok: string, kind: "capacity" | "triage") {
    setCustomBusy(true);
    setError(null);
    try {
      if (kind === "capacity") setCapacity(await getCapacityLatest(tok));
      else setTriage(await getTriageLatest(tok));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    } finally {
      setCustomBusy(false);
    }
  }

  async function runCustom(kind: "capacity" | "triage") {
    if (!token) return;
    setCustomBusy(true);
    setError(null);
    try {
      if (kind === "capacity") setCapacity(await runCapacity(token));
      else setTriage(await runTriage(token));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Run failed");
    } finally {
      setCustomBusy(false);
    }
  }

  async function enter(slug: string) {
    const chosen = TENANTS.find((t) => t.slug === slug) ?? TENANTS[0];
    setTenant(chosen);
    setError(null);
    try {
      const tok = await getDevToken(slug);
      tokenRef.current = tok;
      setRealAuth(false);
      setMe(null);
      setToken(tok);
      await loadLatest(tok, "routing"); // default section is Dispatch
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign-in failed");
    }
  }

  async function refetchMe(tok?: string) {
    const t = tok ?? tokenRef.current;
    if (!t) return;
    try {
      setMe(await getMe(t));
    } catch {
      /* keep the last known profile — /v1 calls surface real auth errors */
    }
  }

  // Real login (Supabase access_token from AuthGate).
  async function enterReal(tok: string) {
    tokenRef.current = tok;
    setRealAuth(true);
    setToken(tok);
    setError(null);
    let profile: Me | null = null;
    try {
      profile = await getMe(tok);
      setMe(profile);
    } catch (e) {
      setMe(null);
      setError(e instanceof Error ? e.message : "Could not load your account");
    }
    // Org-linked accounts open on the Organization Brain (the demo wow screen); everyone else lands
    // on the first section they can see. Never fetch an out-of-scope agent (no 403 spam).
    const sections = profile?.allowed_sections ?? null;
    const start: Section = profile?.person
      ? "organization"
      : sectionAllowed(sections, "dispatch") ? "dispatch" : firstAllowedSection(sections);
    setSection(start);
    const a = SECTION_AGENT[start];
    if (a && agentAllowed(profile?.allowed_agents ?? null, a)) await loadLatest(tok, a);
  }

  // SecurityPanel hands up a refreshed token after 2FA enroll/unenroll (the old one keeps the old AAL).
  function handleNewToken(tok: string) {
    tokenRef.current = tok;
    setToken(tok);
  }

  function go(next: Section) {
    // Server-mirrored nav guard: never navigate a department-scoped login to a section outside its
    // scope (the redirect effect would only bounce it back with a confusing 403 flash).
    if (effectiveSections && !effectiveSections.includes(next)) return;
    setSection(next);
    const a = SECTION_AGENT[next];
    if (token && a && !loaded.has(a) && agentAllowed(effectiveAgents, a)) void loadLatest(token, a);
    if (token && next === "capacity" && !capacity) void loadCustom(token, "capacity");
    if (token && next === "dispatchboard" && !triage) void loadCustom(token, "triage");
  }

  async function run() {
    if (!token || !agent) return;
    setPending(agent);
    setError(null);
    try {
      const res = await runAgent<AgentResult>(token, agent, RUN_QUERY[agent] ?? "");
      setData((d) => ({ ...d, [agent]: res }));
      setLoaded((s) => new Set(s).add(agent));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Run failed");
    } finally {
      setPending(null);
    }
  }

  function signOut() {
    if (realAuth) void activeSupabase()?.auth.signOut();
    tokenRef.current = null;
    setToken(null);
    setMe(null);
    setRealAuth(false);
    setSecurityOpen(false);
    setSimulated(null);
    setData(EMPTY_DATA);
    setLoaded(new Set());
    setSection("dispatch");
    setError(null);
  }

  if (!token)
    return (
      <AuthGate
        tenants={TENANTS}
        error={error}
        busy={pending !== null}
        light={light}
        onTheme={() => setLight((v) => !v)}
        onEnter={enter}
        onAuthed={enterReal}
      />
    );

  const meta = NAV.flatMap((g) => g.items).find((i) => i.key === section)!;
  const busy = agent ? pending === agent : false;
  const current = agent ? data[agent] : null;
  // Customers never see the Operator group; it renders only in super-admin mode (?superadmin=1).
  // Department-scoped accounts additionally see only their allowed sections (Operator keeps its own gating;
  // allowed_sections never includes email/seo). While simulating, Operator hides too — the banner
  // promises "exactly what this login sees".
  const allowedSections = effectiveSections;
  const nav = (superAdmin && !simulated ? NAV : NAV.filter((g) => g.group !== "Operator"))
    .map((g) =>
      g.group === "Operator" || !allowedSections
        ? g
        : { ...g, items: g.items.filter((i) => allowedSections.includes(i.key)) },
    )
    .filter((g) => g.items.length > 0);
  const supabase = realAuth ? activeSupabase() : null;
  // The View-As control renders only for an unrestricted REAL principal (dev tokens: me = null;
  // executive/admin logins: allowed_sections = null). Restricted logins never see it.
  const unrestricted = !me?.allowed_sections;

  return (
    <div className="mx-auto max-w-7xl px-5 py-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-accent/15 text-accent ring-1 ring-accent/30">
            <Spark />
          </div>
          <div>
            <div className="text-sm font-semibold tracking-tight text-zinc-100">Top Builder AI</div>
            <div className="text-xs text-zinc-500">
              {simulated ? (
                <span className="flex items-center gap-1.5">
                  <span className="font-medium uppercase tracking-wide text-accent-soft">Viewing as</span>
                  <span>{simulated.name} · {simulated.title}</span>
                  <DeptChip dept={simulated.department} />
                </span>
              ) : realAuth && me ? (
                me.person ? (
                  <span className="flex items-center gap-1.5">
                    <span>{me.person.full_name} · {me.person.title}</span>
                    {me.department && <DeptChip dept={me.department} />}
                  </span>
                ) : (
                  `${me.tenant_name} · ${me.email}`
                )
              ) : (
                `${tenant.name} · operating layer`
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {unrestricted && <ViewAsControl token={token} active={simulated} onChange={setSimulated} />}
          <button className="btn-ghost" onClick={() => setLight((v) => !v)} title="Toggle theme">
            {light ? "◐ Easy mode" : "◑ Command"}
          </button>
          {realAuth && me && (
            <button className="btn-ghost" onClick={() => setSecurityOpen(true)} title="Security settings" data-testid="security-open">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
                <path d="M12 3l7 3v5c0 4.6-3 8.6-7 10-4-1.4-7-5.4-7-10V6l7-3Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
              </svg>
              Security
            </button>
          )}
          {agent && (
            <button className="btn-primary" onClick={run} disabled={busy}>
              {busy ? <Spinner /> : <Spark />}
              {busy ? "Analyzing…" : `Run ${meta.label.toLowerCase()}`}
            </button>
          )}
          <button className="btn-ghost" onClick={signOut}>{realAuth ? "Sign out" : "Exit demo"}</button>
        </div>
      </header>

      {realAuth && me?.two_factor_required && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-sm text-amber-200">
          <span>Operator access requires 2FA — set it up now.</span>
          <button
            className="rounded-md border border-amber-500/40 px-2.5 py-1 text-xs font-medium text-amber-200 hover:bg-amber-500/20"
            onClick={() => setSecurityOpen(true)}
            data-testid="banner-setup-2fa"
          >
            Set up 2FA
          </button>
        </div>
      )}

      {simulated && (
        <div
          className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-accent/30 bg-accent/10 px-4 py-2.5 text-sm text-accent-soft"
          data-testid="viewas-banner"
        >
          <span>
            Viewing as <span className="font-semibold">{simulated.name}</span> — {simulated.title}. This is exactly what this login sees.
          </span>
          <button
            className="rounded-md border border-accent/40 px-2.5 py-1 text-xs font-medium text-accent-soft hover:bg-accent/20"
            onClick={() => setSimulated(null)}
            data-testid="viewas-exit"
          >
            Exit
          </button>
        </div>
      )}

      <div className="mt-6 flex flex-col gap-6 lg:flex-row">
        <aside className="lg:w-56 lg:shrink-0">
          <nav className="space-y-4">
            {nav.map((g) => (
              <div key={g.group}>
                <div className="label mb-1.5 px-1">{g.group}</div>
                <div className="flex gap-1 overflow-x-auto lg:flex-col lg:gap-0.5">
                  {g.items.map((it) => (
                    <button
                      key={it.key}
                      data-testid={`nav-${it.key}`}
                      onClick={() => go(it.key)}
                      className={`shrink-0 rounded-lg px-3 py-2 text-left text-sm font-medium transition lg:w-full ${
                        it.key === section ? "bg-accent/15 text-accent" : "text-zinc-400 hover:bg-white/[0.04] hover:text-zinc-200"
                      }`}
                    >
                      {it.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </nav>
        </aside>

        <main className="min-w-0 flex-1">
          <div className="mb-4">
            <h1 className="text-lg font-semibold tracking-tight text-zinc-100">{meta.label}</h1>
            <p className="text-sm text-zinc-500">{meta.blurb}</p>
          </div>

          {error && (
            <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>
          )}

          {section === "organization" ? (
            <OrgBrainView token={token} />
          ) : section === "executive" ? (
            <ExecutiveView token={token} />
          ) : section === "kpitrends" ? (
            <KpiTrendsView token={token} />
          ) : section === "frontdesk" ? (
            <FrontDeskView token={token} />
          ) : section === "approvals" ? (
            <ApprovalsView token={token} onOpenSection={(s) => go(s as Section)} allowedSections={effectiveSections} />
          ) : section === "controls" ? (
            <AgentControls token={token} />
          ) : section === "learning" ? (
            <LearningView token={token} />
          ) : section === "email" ? (
            <EmailView token={token} />
          ) : section === "seo" ? (
            <SeoView token={token} />
          ) : section === "adscrm" ? (
            <AdsCrmView token={token} />
          ) : section === "collections" ? (
            <CollectionsView token={token} />
          ) : section === "pricebook" ? (
            <PricebookView token={token} />
          ) : section === "issues" ? (
            <IssuesView token={token} />
          ) : section === "businessplan" ? (
            <BusinessPlanView token={token} />
          ) : section === "capacity" ? (
            capacity ? (
              <CapacityView data={capacity} />
            ) : (
              <EmptyState title="No capacity run yet" body={meta.blurb} busy={customBusy} onRun={() => void runCustom("capacity")} />
            )
          ) : section === "dispatchboard" ? (
            triage ? (
              <DispatchBoardView data={triage} />
            ) : (
              <EmptyState title="No dispatch board yet" body={meta.blurb} busy={customBusy} onRun={() => void runCustom("triage")} />
            )
          ) : busy && !current ? (
            <div className="panel grid place-items-center px-6 py-20 text-zinc-500">
              <Spinner />
              <span className="mt-3 text-sm">Loading {meta.label.toLowerCase()}…</span>
            </div>
          ) : !current ? (
            <EmptyState title={`No ${meta.label.toLowerCase()} run yet`} body={meta.blurb} busy={busy} onRun={run} />
          ) : section === "dispatch" ? (
            <DispatchView data={current as RoutingRunResult} />
          ) : section === "workforce" ? (
            <WorkforceView data={current as WorkforceRunResult} />
          ) : section === "financial" ? (
            <FinancialView data={current as FinancialRunResult} />
          ) : section === "inventory" ? (
            <InventoryView data={current as InventoryRunResult} token={token} />
          ) : section === "booking" ? (
            <BookingView data={current as BookingRunResult} />
          ) : (
            <DocumentsView data={current as DocumentsRunResult} />
          )}

          {current && agent && (
            <footer className="flex flex-wrap items-center justify-between gap-2 pt-6 text-xs text-zinc-600">
              <span className="num">
                run {(current as { run_id?: string | null }).run_id?.slice(0, 8)} · inputs {current.inputs_hash.slice(0, 12)}
              </span>
              <span>Advisory by default — Top Builder AI proposes; you approve.</span>
            </footer>
          )}
        </main>
      </div>

      <AssistantDock token={token} userName={me?.person?.full_name.split(" ")[0] ?? null} />

      {securityOpen && me && supabase && (
        <SecurityPanel
          supabase={supabase}
          me={me}
          onClose={() => setSecurityOpen(false)}
          onAalChanged={() => void refetchMe()}
          onToken={handleNewToken}
        />
      )}
    </div>
  );
}
