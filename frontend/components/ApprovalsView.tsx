"use client";

import { Fragment, useCallback, useEffect, useState } from "react";

import { Badge, Panel, Spinner } from "@/components/ui";
import { approveAndExecuteAction, listActions, rejectAction, type ActionRow } from "@/lib/api";

// Money/legal kinds (mirrors backend ALWAYS_HITL_KINDS) flagged in the inbox as "lead approval".
const MONEY_LEGAL = new Set([
  "payroll_adjustment", "place_dunning_call", "send_dunning_sms", "send_dunning_email",
  "create_ap_draft", "register_warranty", "update_pricebook_item",
  "ads.create_campaign", "ads.update_budget", "ads.activate_campaign",
]);

// ---------------------------------------------------------------------------------------------
// Take-me-there navigation: each action kind lives in a Command Center view (derived from the
// backend KIND_OWNER map in app/actions/ownership.py, then owning agent -> section). Kinds with
// no confident home get no button rather than a wrong jump.
// ---------------------------------------------------------------------------------------------
const KIND_SECTION: Record<string, string> = {
  payroll_adjustment: "workforce",
  send_dunning_email: "collections", send_dunning_sms: "collections", place_dunning_call: "collections",
  update_pricebook_item: "pricebook",
  create_ap_draft: "documents", register_warranty: "documents",
  file_document: "documents", request_signature: "documents",
  book_appointment: "frontdesk", create_estimate: "frontdesk", // booking queue + tasks live in Front Desk
  send_email_reply: "email", delete_emails: "email", rewrite_workflow: "email",
  publish_blog_post: "seo", post_comment: "seo",
  send_outreach_email: "adscrm", // the leads pipeline (ADR 0009) is the outreach surface
  "ads.create_campaign": "adscrm", "ads.update_budget": "adscrm", "ads.activate_campaign": "adscrm",
  "ads.pause_campaign": "adscrm", "ads.sync_conversion": "adscrm",
};

// Fallback for unmapped kinds: the action's owning agent -> the section where that agent lives.
const AGENT_SECTION: Record<string, string> = {
  workforce: "workforce", financial: "financial", collections: "collections", inventory: "inventory",
  booking: "frontdesk", routing: "dispatch", documents: "documents", pricebook: "pricebook",
  email: "email", seo: "seo", ads: "adscrm", fieldops: "frontdesk",
};

const SECTION_LABEL: Record<string, string> = {
  workforce: "Workforce", financial: "Financial", collections: "Collections", inventory: "Inventory",
  frontdesk: "Front Desk", dispatch: "Dispatch", documents: "Documents", pricebook: "Pricebook",
  email: "Email", seo: "SEO & Content", adscrm: "Ads & CRM",
};

function targetView(kind: string, agent: string): { section: string; label: string } | null {
  const section = KIND_SECTION[kind] ?? AGENT_SECTION[agent];
  if (!section) return null;
  return { section, label: SECTION_LABEL[section] ?? section };
}

// ---------------------------------------------------------------------------------------------
// Kind-aware one-line summaries: every registered action kind gets a genuinely informative line
// built from its real param names (see backend app/actions/executors.py + each agent's proposer).
// ---------------------------------------------------------------------------------------------
type P = Record<string, unknown>;

const fmtUsd = (dollars: number): string =>
  dollars.toLocaleString("en-US", {
    style: "currency", currency: "USD",
    minimumFractionDigits: Number.isInteger(dollars) ? 0 : 2, maximumFractionDigits: 2,
  });

const cents = (v: unknown): string | undefined =>
  typeof v === "number" && Number.isFinite(v) ? fmtUsd(v / 100) : undefined;

const scalar = (v: unknown): string | undefined =>
  typeof v === "string" && v.trim() !== "" ? v : typeof v === "number" || typeof v === "boolean" ? String(v) : undefined;

const withLabel = (label: string, v: unknown): string | undefined => {
  const val = scalar(v);
  return val === undefined ? undefined : `${label} ${val}`;
};

const quoted = (v: unknown): string | undefined => {
  const val = scalar(v);
  if (val === undefined) return undefined;
  return `"${val.length > 60 ? `${val.slice(0, 60)}…` : val}"`;
};

const join = (...parts: Array<string | undefined>): string | undefined => {
  const xs = parts.filter((x): x is string => typeof x === "string" && x !== "");
  return xs.length ? xs.join(" · ") : undefined;
};

const asObj = (v: unknown): P => (v && typeof v === "object" && !Array.isArray(v) ? (v as P) : {});

const dunning = (verb: string) => (p: P): string | undefined => {
  const bal = typeof p.balance_usd === "number" ? `${fmtUsd(p.balance_usd)} overdue` : undefined;
  const late = typeof p.days_overdue === "number" ? `${p.days_overdue} days late` : undefined;
  return join(
    `${verb} ${scalar(p.customer_name) ?? scalar(p.customer_id) ?? "customer"}`,
    bal, late, withLabel("step", p.dunning_step),
  );
};

const KIND_SUMMARY: Record<string, (p: P) => string | undefined> = {
  book_appointment: (p) =>
    join(`Book ${scalar(p.caller_name) ?? "inbound caller"}`, scalar(p.trade),
      withLabel("for", p.proposed_date), withLabel("intake", p.intake_id)),
  create_estimate: (p) => {
    const total = cents(p.total_cents);
    const n = Array.isArray(p.lines) ? p.lines.length : undefined;
    return join(`Create estimate${total ? ` for ${total}` : ""}`, withLabel("job", p.job_ref),
      withLabel("customer", p.customer_name), n !== undefined ? `${n} line item${n === 1 ? "" : "s"}` : undefined);
  },
  file_document: (p) => {
    const dept = scalar(p.department);
    const folder = scalar(p.st_folder);
    return join(`File ${scalar(p.doc_number) ?? scalar(p.doc_id) ?? "document"}`,
      dept && folder ? `to ${dept}/${folder}` : withLabel("to", folder ?? dept),
      withLabel("customer", p.customer_ref ?? p.customer_name));
  },
  request_signature: (p) =>
    join(`Send ${scalar(p.doc_number) ?? scalar(p.doc_id) ?? "document"} for e-signature`,
      withLabel("customer", p.customer_ref ?? p.customer_name)),
  send_email_reply: (p) =>
    join(`Reply to ${scalar(p.to_name) ?? scalar(p.to_address) ?? scalar(p.email_id) ?? "sender"}`,
      quoted(p.draft_subject)),
  delete_emails: (p) => {
    const n = Array.isArray(p.email_ids) ? p.email_ids.length : undefined;
    return n === undefined ? undefined : `Move ${n} email${n === 1 ? "" : "s"} to trash`;
  },
  rewrite_workflow: (p) => {
    const subj = quoted(p.subject);
    return join(`Rewrite workflow ${scalar(p.name) ?? scalar(p.workflow_id) ?? ""}`.trim(),
      subj ? `new subject ${subj}` : undefined, scalar(p.instruction));
  },
  publish_blog_post: (p) =>
    join(`Publish ${quoted(p.title) ?? "blog post"}`, withLabel("keyword", p.keyword), withLabel("slug", p.slug)),
  post_comment: (p) =>
    join(`Post comment on ${scalar(p.thread_title) ?? scalar(p.url) ?? "thread"}`, withLabel("platform", p.platform)),
  payroll_adjustment: (p) => {
    const gap = typeof p.hours_discrepancy === "number" ? `${p.hours_discrepancy}h discrepancy` : undefined;
    const claim = typeof p.claimed_hours === "number" && typeof p.computed_hours === "number"
      ? `${p.claimed_hours}h claimed vs ${p.computed_hours}h clocked` : undefined;
    const period = scalar(p.period_start) && scalar(p.period_end)
      ? `${scalar(p.period_start)} to ${scalar(p.period_end)}` : undefined;
    return join(`Adjust pay for ${scalar(p.worker_name) ?? scalar(p.worker_id) ?? "worker"}`, gap, claim, period);
  },
  create_ap_draft: (p) =>
    join(`Draft A/P ${cents(p.amount_cents) ?? "entry"} to ${scalar(p.vendor) ?? "vendor"}`,
      withLabel("job", p.job_ref), withLabel("invoice", p.doc_number)),
  register_warranty: (p) =>
    join(`Register ${scalar(p.equipment_id) ?? "equipment"} for warranty`,
      withLabel("portal", p.portal), withLabel("job", p.job_ref)),
  send_dunning_email: dunning("Email"),
  send_dunning_sms: dunning("Text"),
  place_dunning_call: dunning("Call"),
  update_pricebook_item: (p) => {
    const from = cents(p.old_price_cents);
    const to = cents(p.new_price_cents);
    const move = from && to ? `${from} → ${to}` : to ? `new price ${to}` : undefined;
    const pct = typeof p.price_delta_pct === "number"
      ? `${p.price_delta_pct > 0 ? "+" : ""}${p.price_delta_pct}%` : undefined;
    return join(`Re-price ${scalar(p.name) ?? scalar(p.code) ?? "item"}`, move, pct);
  },
  send_outreach_email: (p) =>
    join(`Email ${scalar(p.to_email) ?? "contact"}`, quoted(p.subject), withLabel("contact", p.contact_id)),
  "ads.create_campaign": (p) => {
    const t = asObj(p.template);
    const acct = asObj(p.ad_account);
    const daily = cents(asObj(t.budget_spec).daily_cents) ?? cents(t.daily_budget_cents);
    return join(
      `Create ${scalar(acct.platform) ?? scalar(p.platform) ?? "ad"} campaign ${quoted(t.name) ?? ""}`.trim(),
      scalar(t.objective), daily ? `${daily}/day` : undefined, "starts paused",
    );
  },
  "ads.update_budget": (p) => {
    const from = cents(p.old_daily_budget_cents);
    const to = cents(p.new_daily_budget_cents);
    return join(
      `Set ${scalar(p.platform) ?? ""} campaign ${scalar(p.campaign_ref) ?? ""} budget`.replace(/\s+/g, " ").trim(),
      from && to ? `${from} → ${to} per day` : to ? `${to} per day` : undefined,
    );
  },
  "ads.activate_campaign": (p) =>
    join(`Activate ${scalar(p.platform) ?? ""} campaign ${scalar(p.campaign_ref) ?? ""}`.replace(/\s+/g, " ").trim(),
      "starts spending"),
  "ads.pause_campaign": (p) =>
    join(`Pause ${scalar(p.platform) ?? ""} campaign ${scalar(p.campaign_ref) ?? ""}`.replace(/\s+/g, " ").trim(),
      "stops spending"),
  "ads.sync_conversion": (p) =>
    join(`Send ${quoted(p.event_name) ?? "conversion"} to ${scalar(p.platform) ?? "ad platform"}`,
      withLabel("dedupe", p.dedupe_key)),
};

/** Generic fallback for unknown kinds: the first few scalar params as "key: value". */
function genericSummary(p: P): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(p)) {
    if (k.startsWith("_")) continue; // server-injected context, not reviewer-facing
    let val = k.endsWith("_cents") ? cents(v)
      : k.endsWith("_usd") && typeof v === "number" ? fmtUsd(v)
      : scalar(v);
    if (val === undefined) continue;
    if (val.length > 40) val = `${val.slice(0, 40)}…`;
    parts.push(`${k.replace(/_/g, " ")}: ${val}`);
    if (parts.length >= 3) break;
  }
  if (parts.length) return parts.join(" · ");
  const n = Object.keys(p).filter((k) => !k.startsWith("_")).length;
  return n ? `${n} detail field${n === 1 ? "" : "s"} attached. Click to review.` : "No details recorded.";
}

function summarize(kind: string, params: P | null | undefined): string {
  if (!params || Object.keys(params).length === 0) return "No details recorded.";
  return KIND_SUMMARY[kind]?.(params) ?? genericSummary(params);
}

// ---------------------------------------------------------------------------------------------
// Expanded-panel param rendering: a clean definition list, money formatted, nested values
// pretty-printed compactly.
// ---------------------------------------------------------------------------------------------
const isScalarArray = (v: unknown): v is Array<string | number | boolean> =>
  Array.isArray(v) && v.every((x) => ["string", "number", "boolean"].includes(typeof x));

function ParamValue({ k, v }: { k: string; v: unknown }) {
  if (v === null || v === undefined || v === "") return <span className="text-zinc-500">not set</span>;
  const money = k.endsWith("_cents") ? cents(v) : k.endsWith("_usd") && typeof v === "number" ? fmtUsd(v) : undefined;
  if (money) return <span className="num text-zinc-100">{money}</span>;
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean")
    return <span className="whitespace-pre-wrap break-words text-zinc-200">{String(v)}</span>;
  if (isScalarArray(v)) return <span className="break-words text-zinc-200">{v.map(String).join(", ")}</span>;
  return (
    <pre className="num max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-lg border border-white/[0.06] bg-white/[0.03] p-2 text-xs text-zinc-300">
      {JSON.stringify(v, null, 1)}
    </pre>
  );
}

/** A wide value (long text / nested object) gets the full row in the definition list. */
const isWide = (v: unknown): boolean =>
  (typeof v === "string" && v.length > 64) || (typeof v === "object" && v !== null && !isScalarArray(v));

export default function ApprovalsView({
  token,
  onOpenSection,
  allowedSections,
}: {
  token: string;
  onOpenSection?: (section: string) => void;
  /** The signed-in user's section scope (null/undefined = unrestricted). The "View in" jump button
   * only renders for sections the reviewer can actually open. */
  allowedSections?: string[] | null;
}) {
  const [rows, setRows] = useState<ActionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await listActions(token, { status: "proposed" }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load your approvals. Try again.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function decide(row: ActionRow, choice: "approve" | "reject") {
    setBusyId(row.id);
    setNote(null);
    setError(null);
    try {
      if (choice === "approve") {
        await approveAndExecuteAction(token, row.id);
        setNote(`Approved: ${row.kind.replace(/_/g, " ")} is done.`);
      } else {
        await rejectAction(token, row.id);
        setNote(`Disapproved: ${row.kind.replace(/_/g, " ")} will not run.`);
      }
      setRows((rs) => rs.filter((r) => r.id !== row.id)); // drop it from the queue
      setOpenId((cur) => (cur === row.id ? null : cur));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't complete that. Try again.");
    } finally {
      setBusyId(null);
    }
  }

  const toggle = (id: string) => setOpenId((cur) => (cur === id ? null : id));

  if (loading && rows.length === 0) {
    return (
      <div className="panel grid place-items-center px-6 py-16 text-zinc-500">
        <Spinner />
        <span className="mt-3 text-sm">Loading your approvals…</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-200">
          {error}
          <button className="ml-3 underline underline-offset-2" onClick={() => void load()}>Retry</button>
        </div>
      )}
      {note && <div className="rounded-xl border border-accent/30 bg-accent/10 px-4 py-2.5 text-sm text-accent-soft">{note}</div>}

      <Panel title="My Approvals" aside={`${rows.length} awaiting you · your department`}>
        {rows.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">Nothing awaiting your approval right now.</p>
        ) : (
          <>
            <p className="border-b border-white/[0.06] px-5 py-2 text-xs text-zinc-500">
              Click any row to review the full details, then approve or jump to where it lives.
            </p>
            <table className="w-full text-sm">
              <thead>
                <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                  <th>Action</th><th>Agent</th><th>Details</th><th>Proposed</th><th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const open = openId === r.id;
                  const summary = summarize(r.kind, r.params);
                  const target = targetView(r.kind, r.agent);
                  const paramEntries = Object.entries(r.params ?? {}).filter(([k]) => !k.startsWith("_"));
                  return (
                    <Fragment key={r.id}>
                      <tr
                        role="button"
                        tabIndex={0}
                        aria-expanded={open}
                        aria-controls={`approval-detail-${r.id}`}
                        onClick={() => toggle(r.id)}
                        onKeyDown={(e) => {
                          if (e.target !== e.currentTarget) return;
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            toggle(r.id);
                          }
                        }}
                        className={`cursor-pointer align-top transition-colors [&>td]:px-5 [&>td]:py-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent/60 ${
                          open ? "bg-white/[0.03]" : "hover:bg-white/[0.02]"
                        }`}
                      >
                        <td className="font-medium text-zinc-100">
                          <span className="flex items-center gap-2">
                            <svg
                              className={`h-3.5 w-3.5 shrink-0 text-zinc-500 transition-transform duration-200 motion-reduce:transition-none ${open ? "rotate-90" : ""}`}
                              viewBox="0 0 24 24" fill="none" aria-hidden
                            >
                              <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                            <span>
                              {r.kind.replace(/_/g, " ")}
                              {MONEY_LEGAL.has(r.kind) && (
                                <span className="ml-2 rounded border border-amber-400/25 bg-amber-400/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-amber-300">
                                  lead approval
                                </span>
                              )}
                            </span>
                          </span>
                        </td>
                        <td><Badge label={r.agent} /></td>
                        <td className="text-zinc-300">
                          <div className="max-w-[360px] truncate" title={summary}>{summary}</div>
                        </td>
                        <td className="num text-zinc-400">{r.created_at ? r.created_at.slice(0, 10) : "not recorded"}</td>
                        <td className="text-right whitespace-nowrap">
                          <button
                            className="btn-primary !px-3 !py-1 text-xs"
                            disabled={busyId === r.id}
                            onClick={(e) => { e.stopPropagation(); void decide(r, "approve"); }}
                          >
                            {busyId === r.id ? "Working…" : "Approve"}
                          </button>
                          <button
                            className="ml-2 rounded-lg border border-white/10 px-3 py-1 text-xs text-zinc-300 hover:border-red-400/40 hover:text-red-200 disabled:opacity-50"
                            disabled={busyId === r.id}
                            onClick={(e) => { e.stopPropagation(); void decide(r, "reject"); }}
                          >
                            Disapprove
                          </button>
                        </td>
                      </tr>
                      {/* Inline review panel: animated height + opacity, no motion under prefers-reduced-motion. */}
                      <tr className="border-b border-white/[0.04] last:border-0">
                        <td colSpan={5} className="p-0">
                          <div
                            id={`approval-detail-${r.id}`}
                            aria-hidden={!open}
                            className={`grid transition-all duration-300 ease-out motion-reduce:transition-none ${
                              open ? "visible [grid-template-rows:1fr] opacity-100" : "invisible [grid-template-rows:0fr] opacity-0"
                            }`}
                          >
                            <div className="overflow-hidden">
                              <div className="mx-5 mb-4 rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-4">
                                <div className="flex flex-wrap items-center gap-2 text-xs">
                                  <Badge label={r.agent} />
                                  <span className="rounded border border-white/10 bg-white/5 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400">
                                    {r.status}
                                  </span>
                                  {MONEY_LEGAL.has(r.kind) && (
                                    <span className="rounded border border-amber-400/25 bg-amber-400/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-amber-300">
                                      lead approval required
                                    </span>
                                  )}
                                  <span className="num ml-auto text-zinc-500">
                                    Proposed {r.created_at ? new Date(r.created_at).toLocaleString() : "at an unknown time"}
                                  </span>
                                </div>

                                {paramEntries.length === 0 ? (
                                  <p className="mt-3 text-sm text-zinc-500">No parameters were recorded with this proposal.</p>
                                ) : (
                                  <dl className="mt-4 grid gap-x-8 gap-y-3 sm:grid-cols-2">
                                    {paramEntries.map(([k, v]) => (
                                      <div key={k} className={isWide(v) ? "sm:col-span-2" : undefined}>
                                        <dt className="label">{k.replace(/_/g, " ")}</dt>
                                        <dd className="mt-1 text-sm"><ParamValue k={k} v={v} /></dd>
                                      </div>
                                    ))}
                                  </dl>
                                )}

                                <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-white/[0.06] pt-3">
                                  {target && onOpenSection && (!allowedSections || allowedSections.includes(target.section)) && (
                                    <button
                                      className="inline-flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent-soft transition hover:bg-accent/20"
                                      onClick={() => onOpenSection(target.section)}
                                    >
                                      View in {target.label}
                                      <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" aria-hidden>
                                        <path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                                      </svg>
                                    </button>
                                  )}
                                  <div className="ml-auto flex gap-2">
                                    <button
                                      className="btn-primary !px-3 !py-1.5 text-xs"
                                      disabled={busyId === r.id}
                                      onClick={() => void decide(r, "approve")}
                                    >
                                      {busyId === r.id ? "Working…" : "Approve"}
                                    </button>
                                    <button
                                      className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-zinc-300 hover:border-red-400/40 hover:text-red-200 disabled:opacity-50"
                                      disabled={busyId === r.id}
                                      onClick={() => void decide(r, "reject")}
                                    >
                                      Disapprove
                                    </button>
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </>
        )}
      </Panel>
    </div>
  );
}
