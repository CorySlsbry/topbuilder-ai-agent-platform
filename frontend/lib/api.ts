import type {
  AccessMatrix,
  AgentMode,
  AgentName,
  AgentOverrideMode,
  AgentPolicy,
  AgentState,
  CapacityRunResult,
  CollectionsRunResult,
  Communication,
  OrgKpis,
  OrgKpiTimeseries,
  OrgOverview,
  OrgPersonProfile,
  PricebookRunResult,
  Scorecard,
  ScorecardTrends,
  Task,
  TriageRunResult,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

// ---- friendly errors (every surface in the app routes failures through here) ----

/** A failed API call, carrying the HTTP status and the server's own message alongside
 * the human-readable message (in `.message`) that components render directly. */
export class ApiError extends Error {
  readonly status: number;
  readonly serverMessage: string | null;
  constructor(status: number, message: string, serverMessage: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.serverMessage = serverMessage;
  }
}

const NETWORK_MESSAGE = "Can't reach the server — check your connection and try again.";

/** Turn an HTTP failure into plain language. `doing` is what the user was trying to do
 * ("switch your field system", "load the inbox") so the message reads like a sentence. */
function friendly(status: number, server: string | null, doing: string): string {
  const s = server ?? "";
  if (status === 401) return "Your session has ended — please sign in again.";
  if (status === 403) {
    if (/2fa|aal2|totp/i.test(s))
      return "This is an operator control — it needs an admin sign-in with two-step verification (set up under Security).";
    if (/does not include the executive/i.test(s))
      return "The Executive view is available to leadership accounts.";
    if (/does not include/i.test(s)) return "Your role doesn't include access to this agent.";
    if (/may not trigger runs/i.test(s)) return "Your sign-in can view results but can't run agents.";
    if (/autonomy is off/i.test(s))
      return "That agent's actions are switched off — turn it on under Agent Controls.";
    if (/execution is disabled|not enabled for execution/i.test(s))
      return "Action execution is turned off for this workspace — an operator can enable it.";
    if (/dev-token is disabled/i.test(s))
      return "The demo sign-in is turned off on this server — use your company login instead.";
    if (/may not approve or execute/i.test(s) || !s) return `Only an operator (admin) can ${doing}.`;
    return `Couldn't ${doing}: ${s}`;
  }
  if (status === 404) return `Couldn't ${doing} — it may have been removed.`;
  if (status === 409) return `Couldn't ${doing} — it changed since you loaded it. Refresh and try again.`;
  if (status === 422)
    return server ? `Couldn't ${doing}: ${server}` : `Couldn't ${doing} — check the values and try again.`;
  if (status === 429) {
    if (/daily/i.test(s)) return "The assistant has hit today's usage limit — it resets tomorrow.";
    return "A lot is happening at once — give it a few seconds and try again.";
  }
  if (status >= 500) return `Couldn't ${doing} — something went wrong on our side. Try again in a moment.`;
  return `Couldn't ${doing} (error ${status}).`;
}

/** Read a failed response into an ApiError. Understands both the API's
 * {"error":{"message":…}} envelope and FastAPI's raw {"detail":…}. */
export async function toApiError(res: Response, doing: string): Promise<ApiError> {
  let server: string | null = null;
  try {
    const body = (await res.json()) as { error?: { message?: unknown }; detail?: unknown };
    const m = body?.error?.message ?? body?.detail;
    if (typeof m === "string" && m) server = m;
  } catch {
    /* non-JSON body */
  }
  return new ApiError(res.status, friendly(res.status, server, doing), server);
}

export async function safeFetch(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch {
    throw new ApiError(0, NETWORK_MESSAGE);
  }
}

export async function getDevToken(tenantSlug: string): Promise<string> {
  const res = await safeFetch(`${API_BASE}/auth/dev-token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tenant_slug: tenantSlug }),
  });
  if (!res.ok) throw await toApiError(res, "start the demo session");
  return (await res.json()).access_token as string;
}

// ---- generic JSON helpers ----
export async function apiRequest<T>(
  token: string, path: string, doing: string, init?: RequestInit,
): Promise<T> {
  const res = await safeFetch(`${API_BASE}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw await toApiError(res, doing);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

/** GET that treats 404 as "nothing yet" instead of an error. */
export async function apiGetOrNull<T>(token: string, path: string, doing: string): Promise<T | null> {
  const res = await safeFetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw await toApiError(res, doing);
  return res.json();
}

export const getAgentLatest = <T,>(token: string, agent: AgentName) =>
  apiGetOrNull<T>(token, `/v1/agents/${agent}/runs/latest`, `load the ${agent} agent`);

export const runAgent = <T,>(token: string, agent: AgentName, query = "") =>
  apiRequest<T>(token, `/v1/agents/${agent}/runs${query ? `?${query}` : ""}`, `run the ${agent} agent`, {
    method: "POST",
  });

const req = apiRequest;
const apiPost = <T,>(t: string, p: string, doing: string, body?: unknown) =>
  req<T>(t, p, doing, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

// ---- operating-layer endpoints ----
export const listComms = (t: string) => req<Communication[]>(t, "/v1/communications", "load the inbox");
export const listTasks = (t: string) => req<Task[]>(t, "/v1/tasks", "load the task list");
export const updateTask = (t: string, id: string, status: string) =>
  req<Task>(t, `/v1/tasks/${id}`, "update that task", { method: "PATCH", body: JSON.stringify({ status }) });
export const getPolicies = (t: string) => req<AgentPolicy[]>(t, "/v1/agents/policies", "load agent controls");
export const getOrgOverview = (t: string) => req<OrgOverview>(t, "/v1/org/overview", "load the organization");
export const getOrgPerson = (t: string, id: string) =>
  req<OrgPersonProfile>(t, `/v1/org/people/${id}`, "load this profile");
export const setPersonAgent = (t: string, id: string, agent_key: string, mode: AgentOverrideMode) =>
  req<{ agents: string[]; agent_states: AgentState[] }>(t, `/v1/org/people/${id}/agents`, "update agent access", {
    method: "PUT",
    body: JSON.stringify({ agent_key, mode }),
  });
export const syncRoster = (t: string) =>
  req<{ synced: number; departed: number; active: number; skipped?: string }>(t, "/v1/org/sync", "sync the roster", {
    method: "POST",
  });
export const getOrgKpis = (t: string) => req<OrgKpis>(t, "/v1/org/kpis", "load the executive view");
export const getOrgKpisTimeseries = (
  t: string,
  opts: { start?: string; end?: string; departments?: string[] } = {},
) => {
  const q = new URLSearchParams();
  if (opts.start) q.set("start", opts.start);
  if (opts.end) q.set("end", opts.end);
  if (opts.departments?.length) q.set("departments", opts.departments.join(","));
  const qs = q.toString();
  return req<OrgKpiTimeseries>(
    t, `/v1/org/kpis/timeseries${qs ? `?${qs}` : ""}`, "load the KPI history",
  );
};
export const getAccessMatrix = (t: string) =>
  req<AccessMatrix>(t, "/v1/org/access-matrix", "load access permissions");

/** The auto-computed department scorecard (the Bloom Growth L10 replacement).
 * Same auth bar as getOrgKpis — a department-scoped login gets 403. */
export const getScorecard = (
  t: string,
  opts: { weeks?: number; departments?: string[] } = {},
) => {
  const q = new URLSearchParams();
  if (opts.weeks) q.set("weeks", String(opts.weeks));
  if (opts.departments?.length) q.set("departments", opts.departments.join(","));
  const qs = q.toString();
  return req<Scorecard>(t, `/v1/org/scorecard${qs ? `?${qs}` : ""}`, "load the scorecard");
};
/** Rolling-year KPI trends + a deterministic forward forecast band (13-week + 6-month seasonal
 * projection). Same unrestricted (leadership/operator) read bar as getScorecard — a department-
 * scoped login gets a 403. */
export const getScorecardTrends = (
  t: string,
  opts: { weeks?: number; forecastWeeks?: number; departments?: string[]; kpis?: string[] } = {},
) => {
  const q = new URLSearchParams();
  if (opts.weeks) q.set("weeks", String(opts.weeks));
  if (opts.forecastWeeks !== undefined) q.set("forecast_weeks", String(opts.forecastWeeks));
  if (opts.departments?.length) q.set("departments", opts.departments.join(","));
  if (opts.kpis?.length) q.set("kpis", opts.kpis.join(","));
  const qs = q.toString();
  return req<ScorecardTrends>(t, `/v1/org/scorecard/trends${qs ? `?${qs}` : ""}`, "load the KPI trends");
};

export const setPolicy = (t: string, agent: string, mode: AgentMode) =>
  req<AgentPolicy>(t, `/v1/agents/policies/${agent}`, "change that agent's autonomy", {
    method: "PUT", body: JSON.stringify({ mode }),
  });

// ---- field-system providers ----
export type ProviderInfo = {
  slug: string;
  display: string;
  segment: string;
  status: string;
  domains?: string[];
  notes?: string;
  auth_kind?: string;
  connect?: string;
};
export type TenantProvider = { provider: string; display: string; segment: string; status: string };

export const getProviders = (t: string) =>
  req<ProviderInfo[]>(t, "/v1/providers", "load the field-system list");
export const getTenantProvider = (t: string) =>
  req<TenantProvider>(t, "/v1/tenant/provider", "load your field system");
export const setTenantProvider = (t: string, provider: string) =>
  req<TenantProvider>(t, "/v1/tenant/provider", "switch the company's field system", {
    method: "PUT", body: JSON.stringify({ provider }),
  });

// ---- Google Drive/Sheets OAuth connect (admin + AAL2 gated server-side) ----
export type OAuthConnect = { provider: string; authorize_url: string };
export const getGoogleConnectUrl = (t: string) =>
  req<OAuthConnect>(t, "/v1/integrations/google/connect", "connect Google Drive");
// ---- QuickBooks Online OAuth connect (admin + AAL2 gated server-side; Intuit's own OAuth, no iPaaS) ----
export const getQuickBooksConnectUrl = (t: string) =>
  req<OAuthConnect>(t, "/v1/integrations/quickbooks/connect", "connect QuickBooks");

// ---- in-app assistant (Claude Sonnet 4.6 tool loop, permission-aware server-side) ----
export type AssistantAction = { tool: string; summary: string };
export type AssistantUsage = { used_today: number; daily_limit: number };
export type AssistantReply = { reply: string; actions: AssistantAction[]; usage: AssistantUsage };
export type ChatMsg = { role: "user" | "assistant"; content: string };

export const assistantChat = (t: string, messages: ChatMsg[]) =>
  req<AssistantReply>(t, "/v1/assistant/chat", "reach the assistant", {
    method: "POST", body: JSON.stringify({ messages }),
  });

// ---- booking-agent phone voice ----
export type VoiceOption = { key: string; label: string; description: string; preview_url: string };

export const getVoiceOptions = (t: string) =>
  req<VoiceOption[]>(t, "/v1/voice/options", "load the voice options");
export const getTenantVoice = (t: string) =>
  req<{ voice: string }>(t, "/v1/tenant/voice", "load your phone voice");
export const setTenantVoice = (t: string, voice: string) =>
  req<{ voice: string }>(t, "/v1/tenant/voice", "change the phone voice", {
    method: "PUT", body: JSON.stringify({ voice }),
  });

// ---- learning governance (Phase C/D) ----
export type Preference = {
  id: string;
  agent: string;
  preference_text: string;
  status: string;
  support_count: number;
  eval_score: number | null;
  rollout_pct: number;
  proposed_by: string;
};
export type DriftSnapshot = {
  id: string;
  agent: string;
  sample_size: number;
  edit_rate: number | null;
  reject_rate: number | null;
  avg_effectiveness: number | null;
  flagged: boolean;
  created_at: string;
};

export const listPreferences = (t: string, agent?: string, status?: string) => {
  const q = new URLSearchParams();
  if (agent) q.set("agent", agent);
  if (status) q.set("status", status);
  const qs = q.toString();
  return req<Preference[]>(t, `/v1/learning/preferences${qs ? `?${qs}` : ""}`, "load learned rules");
};
export const approvePreference = (t: string, id: string, rolloutPct = 100, force = false) =>
  apiPost<{ preference: Preference; eval: Record<string, unknown> }>(
    t, `/v1/learning/preferences/${id}/approve`, "approve this rule", { rollout_pct: rolloutPct, force },
  );
export const rejectPreference = (t: string, id: string) =>
  apiPost<Preference>(t, `/v1/learning/preferences/${id}/reject`, "reject this rule");
export const retirePreference = (t: string, id: string) =>
  apiPost<Preference>(t, `/v1/learning/preferences/${id}/retire`, "retire this rule");
export const setRollout = (t: string, id: string, rolloutPct: number) =>
  req<Preference>(t, `/v1/learning/preferences/${id}/rollout`, "change the rollout", {
    method: "PUT", body: JSON.stringify({ rollout_pct: rolloutPct }),
  });
export const listDrift = (t: string, agent?: string) =>
  req<DriftSnapshot[]>(t, `/v1/learning/drift${agent ? `?agent=${agent}` : ""}`, "load drift monitoring");
export const runConsolidation = (t: string, agent?: string) =>
  apiPost<{ reports: Record<string, unknown>[] }>(
    t, `/v1/learning/consolidate${agent ? `?agent=${agent}` : ""}`, "run consolidation",
  );

export type ActionResult = { id: string; status: string; result?: Record<string, unknown> };

/** Propose → approve → execute a booking write (handles both hitl and auto policies). */
export async function approveAndBook(
  token: string,
  runId: string | null,
  booking: { intake_id: string; trade: string; proposed_date: string; caller_name: string | null },
): Promise<ActionResult> {
  const action = await apiPost<ActionResult>(token, "/v1/actions", "book this appointment", {
    agent: "booking",
    kind: "book_appointment",
    run_id: runId,
    params: {
      intake_id: booking.intake_id,
      trade: booking.trade,
      proposed_date: booking.proposed_date,
      caller_name: booking.caller_name,
    },
  });
  if (action.status === "executed") return action; // auto-mode already booked it
  await apiPost(token, `/v1/actions/${action.id}/approve`, "approve this booking");
  return apiPost<ActionResult>(token, `/v1/actions/${action.id}/execute`, "book this appointment");
}

// ---- A/R Collections agent ----
export const getCollections = (t: string) =>
  apiGetOrNull<CollectionsRunResult>(t, "/v1/agents/collections/runs/latest", "load collections");
export const runCollections = (t: string, force = false) =>
  apiPost<CollectionsRunResult>(
    t, `/v1/agents/collections/runs${force ? "?force=true" : ""}`, "run the collections agent",
  );

// ---- Pricebook agent (cost-driven re-pricing under the sold-hour model) ----
export const getPricebookLatest = (t: string) =>
  apiGetOrNull<PricebookRunResult>(t, "/v1/agents/pricebook/runs/latest", "load the pricebook");
export const runPricebook = (t: string, force = false) =>
  apiPost<PricebookRunResult>(
    t, `/v1/agents/pricebook/runs${force ? "?force=true" : ""}`, "run the pricebook agent",
  );

/**
 * Propose → approve → execute a recomputed PRICE write for one pricebook item (the "Approve & update"
 * button). The endpoint assembles the kind + params SERVER-SIDE from the persisted run (the engine-
 * computed old/new price), so the caller only names the item code. Pricebook updates are ALWAYS
 * human-in-the-loop, so this never auto-executes — the operator clicking the button IS the approval.
 * If approve/execute is gated (actions disabled, or a non-admin login), the friendly error surfaces and
 * the proposed action remains for an operator to apply under Agent Controls.
 */
export async function proposePricebookUpdate(
  token: string,
  runId: string,
  code: string,
): Promise<ActionResult> {
  const action = await apiPost<ActionResult>(
    token, `/v1/agents/pricebook/runs/${runId}/update`, "update this price",
    { code },
  );
  if (action.status === "executed") return action; // (pricebook is always-hitl, so this won't happen)
  await apiPost(token, `/v1/actions/${action.id}/approve`, "approve this price update");
  return apiPost<ActionResult>(token, `/v1/actions/${action.id}/execute`, "update this price");
}

// ---- Capacity / Overtime (Workforce capacity engine; own endpoint, not the generic runs path) ----
export const getCapacityLatest = (t: string) =>
  apiGetOrNull<CapacityRunResult>(t, "/v1/agents/workforce/capacity/latest", "load the capacity view");
export const runCapacity = (t: string) =>
  apiPost<CapacityRunResult>(t, "/v1/agents/workforce/capacity", "run the capacity analysis");

// ---- Dispatch triage (P1/P2/P3 board; own endpoint under the routing agent) ----
export const getTriageLatest = (t: string) =>
  apiGetOrNull<TriageRunResult>(t, "/v1/agents/routing/triage/latest", "load the dispatch board");
export const runTriage = (t: string) =>
  apiPost<TriageRunResult>(t, "/v1/agents/routing/triage", "run dispatch triage");

/** Read one agent's current autonomy mode (off | hitl | auto). */
export const getAgentPolicy = (t: string, agent: string) =>
  req<AgentPolicy>(t, `/v1/agents/policies/${agent}`, "load that agent's autonomy");

/**
 * Propose → approve → execute a dunning step for a worklist customer (the "Approve & send" button).
 * The endpoint assembles the kind + params SERVER-SIDE from the persisted run (channel, draft,
 * step), so the caller only names the customer. Mirrors approveAndBook: an 'auto' collections agent
 * already executed; otherwise this approves + executes (the operator clicking the button IS the
 * approval). If approve/execute is gated (actions disabled, or a non-admin login), the friendly
 * error surfaces and the proposed action remains for an operator to send under Agent Controls.
 */
export async function proposeDunning(
  token: string,
  runId: string,
  customerId: string,
): Promise<ActionResult> {
  const action = await apiPost<ActionResult>(
    token, `/v1/agents/collections/runs/${runId}/dunning`, "send this dunning step",
    { customer_id: customerId },
  );
  if (action.status === "executed") return action; // auto-mode already sent it
  await apiPost(token, `/v1/actions/${action.id}/approve`, "approve this dunning step");
  return apiPost<ActionResult>(token, `/v1/actions/${action.id}/execute`, "send this dunning step");
}

// ====================================================================================================
// Ads & CRM (ADR 0009) — OPERATOR-ONLY. Every route is gated server-side to a platform operator
// (admin + 2FA + the platform-operator allowlist); a non-operator login gets a 403 that the friendly
// layer renders as "Only an operator (admin) can …". Money is integer CENTS at the API boundary.
// ====================================================================================================

/** A pipeline stage. The DB CHECK constraint allows exactly these six. */
export type LeadStage = "new" | "contacted" | "booked" | "demoed" | "won" | "lost";
export const LEAD_STAGES: LeadStage[] = ["new", "contacted", "booked", "demoed", "won", "lost"];

export type CrmLead = {
  id: string;
  contact_id: string | null;
  stage: LeadStage;
  source: string;
  value_cents: number;
  /** utm_source/medium/campaign/term/content (whichever the lead carried). */
  utm: Record<string, string | undefined>;
  /** {platform, campaign_id, ad_id, lead_id, show, …} — the ad attribution. */
  ad_ref: Record<string, string | undefined>;
  lost_reason: string | null;
  owner: string | null;
  created_at: string;
  updated_at: string;
};

export type CrmActivity = {
  id: string;
  lead_id: string;
  kind: string; // note | stage_change | email | call | booking | system
  body: string | null;
  detail: Record<string, unknown>;
  actor: string | null;
  created_at: string;
};

export type AdAccount = {
  id: string;
  platform: "meta" | "google";
  external_account_id: string;
  display_name: string | null;
  vault_credential_id: string | null;
  status: "disconnected" | "connected" | "error";
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AdTemplate = {
  id: string;
  slug: string;
  name: string;
  template_type: string;
  objective: string; // traffic | leads
  geo_spec: Record<string, unknown>;
  targeting_spec: Record<string, unknown>;
  schedule_spec: Record<string, unknown>;
  budget_spec: Record<string, unknown>;
  creative_spec: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AdCampaign = {
  id: string;
  template_id: string | null;
  ad_account_id: string | null;
  platform: "meta" | "google";
  name: string;
  status: "draft" | "paused" | "active" | "ended" | "error";
  external_campaign_id: string | null;
  external_ids: Record<string, unknown>;
  daily_budget_cents: number;
  lifetime_cap_cents: number;
  spend_cents: number;
  start_at: string | null;
  end_at: string | null;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AdMetric = {
  id: string;
  campaign_id: string;
  day: string; // ISO date
  impressions: number;
  clicks: number;
  landing_page_views: number;
  leads: number;
  spend_cents: number;
  raw: Record<string, unknown>;
  created_at: string;
};

/** What POST /v1/ads/campaigns/build returns — a PROPOSED ads.create_campaign action (inert until approved). */
export type BuildCampaignProposal = {
  action_id: string;
  status: string;
  platform: "meta" | "google";
  campaign_name: string;
  daily_budget_cents: number;
  lifetime_cap_cents: number;
};

// ---- CRM ----
export const listLeads = (t: string, stage?: LeadStage) =>
  req<{ leads: CrmLead[] }>(
    t, `/v1/crm/leads${stage ? `?stage=${stage}` : ""}`, "load the pipeline",
  ).then((r) => r.leads);

export const getLead = (t: string, id: string) =>
  req<{ lead: CrmLead; activities: CrmActivity[] }>(t, `/v1/crm/leads/${id}`, "open this lead");

export const setLeadStage = (t: string, id: string, stage: LeadStage, lostReason?: string) =>
  req<{ lead: CrmLead }>(t, `/v1/crm/leads/${id}/stage`, "move this lead", {
    method: "PATCH",
    body: JSON.stringify({ stage, lost_reason: lostReason ?? null }),
  }).then((r) => r.lead);

export const addLeadActivity = (t: string, id: string, body: string, kind = "note") =>
  apiPost<{ activity: CrmActivity }>(
    t, `/v1/crm/leads/${id}/activities`, "log this activity", { kind, body },
  ).then((r) => r.activity);

// ---- Ads ----
export const listAdAccounts = (t: string) =>
  req<{ accounts: AdAccount[] }>(t, "/v1/ads/accounts", "load ad accounts").then((r) => r.accounts);

export const listAdTemplates = (t: string) =>
  req<{ templates: AdTemplate[] }>(t, "/v1/ads/templates", "load campaign templates").then((r) => r.templates);

export const listAdCampaigns = (t: string, status?: string) =>
  req<{ campaigns: AdCampaign[] }>(
    t, `/v1/ads/campaigns${status ? `?status=${status}` : ""}`, "load campaigns",
  ).then((r) => r.campaigns);

export const getCampaignMetrics = (t: string, id: string) =>
  req<{ campaign: AdCampaign; metrics: AdMetric[] }>(
    t, `/v1/ads/campaigns/${id}/metrics`, "load campaign metrics",
  );

/** Connect an ad platform — returns the operator-OAuth authorize URL (the SPA redirects to it). */
export const getAdConnectUrl = (t: string, provider: "meta" | "google_ads") =>
  req<OAuthConnect>(
    t, `/v1/integrations/${provider}/connect`,
    `connect ${provider === "meta" ? "Meta" : "Google Ads"}`,
  );

/**
 * Build a campaign from a template against a connected ad account: PROPOSE the ads.create_campaign
 * action through the human-approved gate (ADR 0007). NOTHING is written to the ad platform — the
 * returned proposal is inert until an operator approves + executes it (the campaign is created PAUSED).
 */
export const buildCampaign = (
  t: string, adAccountId: string, opts: { templateId?: string; templateSlug?: string },
) =>
  apiPost<BuildCampaignProposal>(t, "/v1/ads/campaigns/build", "build this campaign", {
    ad_account_id: adAccountId,
    template_id: opts.templateId ?? null,
    template_slug: opts.templateSlug ?? null,
  });

/**
 * Approve + execute an already-proposed ad-platform action (the second half of the gate). The build
 * step PROPOSES; this step is the operator's explicit approval — it APPROVES then EXECUTES the real
 * write (for create, that only assembles the PAUSED campaign — money never starts here).
 */
export async function approveAndExecuteAction(t: string, actionId: string): Promise<ActionResult> {
  await apiPost(t, `/v1/actions/${actionId}/approve`, "approve this action");
  return apiPost<ActionResult>(t, `/v1/actions/${actionId}/execute`, "run this action");
}

/** A proposed/decided action row for the My-Approvals inbox (mirrors backend ActionOut). */
export type ActionRow = {
  id: string;
  run_id?: string | null;
  agent: string;
  kind: string;
  status: string;
  params?: Record<string, unknown> | null;
  requested_by?: string | null;
  created_at?: string;
};

/** The caller's approvals queue — server-filtered to the principal's department (My Approvals). */
export const listActions = (t: string, opts?: { agent?: string; status?: string; limit?: number }) => {
  const qs = new URLSearchParams();
  if (opts?.agent) qs.set("agent", opts.agent);
  if (opts?.status) qs.set("status", opts.status);
  if (opts?.limit) qs.set("limit", String(opts.limit));
  const q = qs.toString();
  return apiRequest<ActionRow[]>(t, `/v1/actions${q ? `?${q}` : ""}`, "load your approvals");
};

/** Disapprove (reject) a proposed action — it is never executed. */
export const rejectAction = (t: string, actionId: string) =>
  apiPost<ActionResult>(t, `/v1/actions/${actionId}/reject`, "disapprove this action");

/**
 * Propose → approve → execute a fresh ad-platform action for an EXISTING campaign (Activate / Pause /
 * Budget). Activating commits money, so this is deliberately a SEPARATE, explicit operator step from
 * Build. The kind + params go through the generic action gate (the same audited, idempotent path the
 * agent writes use); a 403 (actions disabled / non-operator) surfaces in plain language.
 */
export async function proposeAdAction(
  t: string,
  kind: "ads.activate_campaign" | "ads.pause_campaign" | "ads.update_budget",
  params: Record<string, unknown>,
  doing: string,
): Promise<ActionResult> {
  const action = await apiPost<ActionResult>(t, "/v1/actions", doing, { agent: "ads", kind, params });
  if (action.status === "executed") return action;
  await apiPost(t, `/v1/actions/${action.id}/approve`, doing);
  return apiPost<ActionResult>(t, `/v1/actions/${action.id}/execute`, doing);
}
