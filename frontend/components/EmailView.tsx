"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge, Confidence, Kpi, Panel, Spark, Spinner, usd } from "@/components/ui";
import { apiGetOrNull, apiRequest } from "@/lib/api";

// ---------------------------------------------------------------------------
// Email agent (#7) — daily inbox briefing.
// Inline response types; fetch + friendly errors come from lib/api.ts.
// Advisory by default — every reply, deletion, and rewrite is proposed only.
// ---------------------------------------------------------------------------

type TopPriority = {
  email_id: string;
  from_name: string;
  subject: string;
  reason: string;
  value_usd: number;
  age_hours: number;
  priority_score: number;
};

type EmailBriefing = {
  unread_total: number;
  needs_reply: number;
  fyi: number;
  trash_candidates: number;
  workflow_reports: number;
  top_priorities: TopPriority[];
};

type ReplyDraft = {
  email_id: string;
  from_name: string;
  subject: string;
  draft_subject: string;
  draft_body: string;
  confidence: number;
  requires_human: boolean;
};

type TrashCandidate = {
  email_id: string;
  from_name: string;
  subject: string;
  category: string;
  age_days: number;
  confidence: number;
};

type ProposedRewrite = { subject: string; preview: string; rationale: string };
type AppliedRewrite = { subject: string; preview: string; applied_by: string; applied_at: string };

type EmailWorkflow = {
  workflow_id: string;
  name: string;
  emails_sent: number;
  open_rate: number;
  reply_rate: number;
  booked_jobs: number;
  benchmark_open_rate: number;
  benchmark_reply_rate: number;
  status: string;
  proposed_rewrite: ProposedRewrite | null;
  /** Copy an operator has actually applied (via the assistant) — distinct from the proposal. */
  applied_rewrite?: AppliedRewrite | null;
};

type EmailRunResult = {
  briefing: EmailBriefing;
  reply_drafts: ReplyDraft[];
  trash_queue: TrashCandidate[];
  workflows: EmailWorkflow[];
  narration: string;
};

const getLatestEmailRun = (token: string) =>
  apiGetOrNull<EmailRunResult>(token, "/v1/agents/email/runs/latest", "load the email briefing");

const runEmailBriefing = (token: string) =>
  apiRequest<EmailRunResult>(token, "/v1/agents/email/runs", "run the email agent", { method: "POST" });

// ---- formatting (rates may arrive as 0–1 fractions or 0–100 — normalize) ----

const toPts = (v: number) => (v <= 1 ? v * 100 : v);
const pct = (v: number) => `${Math.round(toPts(v))}%`;
const score = (v: number) => Math.round(toPts(v));
const age = (hours: number) => (hours < 48 ? `${Math.round(hours)}h` : `${Math.round(hours / 24)}d`);

function RateDelta({ value, benchmark }: { value: number; benchmark: number }) {
  const d = Math.round(toPts(value) - toPts(benchmark));
  const cls =
    d < 0
      ? "border-red-300/25 bg-red-300/10 text-red-300"
      : "border-emerald-300/20 bg-emerald-300/10 text-emerald-300";
  return (
    <span className={`num ml-1.5 inline-flex rounded border px-1 py-0.5 text-[10px] font-medium ${cls}`}>
      {d < 0 ? "▼" : "▲"} {Math.abs(d)} pts
    </span>
  );
}

function WorkflowStatus({ value }: { value: string }) {
  const under = /under|behind|lag|risk|fail/i.test(value);
  const cls = under
    ? "text-red-300 bg-red-300/10 border-red-300/20"
    : "text-emerald-300 bg-emerald-300/10 border-emerald-300/20";
  return (
    <span className={`inline-flex rounded-md border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${cls}`}>
      {value.replace(/_/g, " ")}
    </span>
  );
}

function NeedsYou() {
  return (
    <span className="ml-2 inline-flex shrink-0 rounded-md border border-amber-300/25 bg-amber-300/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-300">
      needs you
    </span>
  );
}

export default function EmailView({ token }: { token: string }) {
  const [data, setData] = useState<EmailRunResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openDrafts, setOpenDrafts] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getLatestEmailRun(token));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      setData(await runEmailBriefing(token));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Email run failed");
    } finally {
      setRunning(false);
    }
  }

  function toggleDraft(id: string) {
    setOpenDrafts((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  if (loading) {
    return (
      <div className="panel grid place-items-center px-6 py-20 text-zinc-500">
        <Spinner />
        <span className="mt-3 text-sm">Loading email…</span>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4">
        {error && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>
        )}
        <div className="panel grid place-items-center px-6 py-16 text-center">
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-accent/15 text-accent ring-1 ring-accent/30">
            <Spark />
          </div>
          <h2 className="mt-4 text-lg font-semibold text-zinc-100">No email briefing yet</h2>
          <p className="mt-1 max-w-sm text-sm text-zinc-500">
            Triage the inbox: priorities, reply drafts, junk cleanup, and outbound workflow health. Proposed only —
            nothing sends without your approval.
          </p>
          <button className="btn-primary mt-5" onClick={run} disabled={running}>
            {running ? <Spinner /> : <Spark />}
            {running ? "Analyzing…" : "Run briefing"}
          </button>
        </div>
      </div>
    );
  }

  const b = data.briefing;
  const humanCount = data.reply_drafts.filter((d) => d.requires_human).length;
  const rewrites = data.workflows.flatMap((w) =>
    w.proposed_rewrite ? [{ workflow: w, rewrite: w.proposed_rewrite }] : [],
  );
  const applied = data.workflows.flatMap((w) =>
    w.applied_rewrite ? [{ workflow: w, rewrite: w.applied_rewrite }] : [],
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-xs text-zinc-500">
          Advisory triage — every reply, deletion, and rewrite below is proposed. Nothing sends without your approval.
        </span>
        <button className="btn-primary" onClick={run} disabled={running}>
          {running ? <Spinner /> : <Spark />}
          {running ? "Analyzing…" : "Run briefing"}
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>
      )}

      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Unread" value={String(b.unread_total)} tone="info" />
        <Kpi label="Needs reply" value={String(b.needs_reply)} tone="warn" />
        <Kpi label="Drafts ready" value={String(data.reply_drafts.length)} tone="ok" />
        <Kpi label="Junk to clear" value={String(b.trash_candidates)} tone="neutral" />
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="panel p-5 lg:col-span-3">
          <h2 className="mb-2 text-sm font-semibold text-zinc-100">Daily briefing</h2>
          <p className="label mb-3">
            {b.fyi} fyi · {b.workflow_reports} workflow reports · deterministic triage, narration only explains
          </p>
          <div className="max-h-[300px] overflow-auto whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-300">
            {data.narration}
          </div>
        </div>
        <div className="panel p-5 lg:col-span-2">
          <h2 className="mb-4 text-sm font-semibold text-zinc-100">Top priorities</h2>
          {b.top_priorities.length === 0 ? (
            <p className="text-sm text-zinc-500">Nothing urgent — the inbox can wait.</p>
          ) : (
            <ul className="space-y-3">
              {b.top_priorities.map((p) => (
                <li key={p.email_id} className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <span className="min-w-0 truncate text-sm font-medium text-zinc-100">{p.subject}</span>
                    {p.value_usd > 0 && (
                      <span className="num shrink-0 rounded-md border border-emerald-300/20 bg-emerald-300/10 px-1.5 py-0.5 text-[11px] font-medium text-emerald-300">
                        {usd(p.value_usd)}
                      </span>
                    )}
                  </div>
                  <div className="mt-1 text-[13px] text-zinc-400">{p.reason}</div>
                  <div className="num mt-1.5 text-[11px] text-zinc-500">
                    {p.from_name} · {age(p.age_hours)} old · priority {score(p.priority_score)}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <Panel
        title="Reply drafts — awaiting your review"
        aside={`${data.reply_drafts.length} proposed${humanCount > 0 ? ` · ${humanCount} need you` : ""}`}
      >
        {data.reply_drafts.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">No replies needed in this batch.</p>
        ) : (
          <ul className="divide-y divide-white/[0.04]">
            {data.reply_drafts.map((d) => {
              const open = openDrafts.has(d.email_id);
              return (
                <li key={d.email_id} className="px-5 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center">
                        <span className="truncate text-sm font-medium text-zinc-100">{d.from_name}</span>
                        {d.requires_human && <NeedsYou />}
                      </div>
                      <div className="truncate text-[13px] text-zinc-400">{d.subject}</div>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <Confidence value={d.confidence} />
                      <button
                        className="btn-ghost !px-3 !py-1 text-xs"
                        onClick={() => toggleDraft(d.email_id)}
                        aria-expanded={open}
                      >
                        {open ? "Hide draft" : "View draft"}
                      </button>
                    </div>
                  </div>
                  {open && (
                    <div className="mt-3 rounded-xl border border-accent/20 bg-accent/[0.05] px-4 py-3">
                      <div className="label mb-1.5">proposed reply — sends only on your approval</div>
                      <div className="text-sm font-medium text-zinc-100">{d.draft_subject}</div>
                      <div className="mt-2 whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-300">
                        {d.draft_body}
                      </div>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Panel>

      <Panel
        title="Inbox cleanup — proposed deletions"
        aside={`${data.trash_queue.length} candidates · cleared only on approval`}
      >
        {data.trash_queue.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">Nothing to clear — the inbox is clean.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                <th>From</th><th>Subject</th><th>Category</th>
                <th className="text-right">Age</th><th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {data.trash_queue.map((q) => (
                <tr key={q.email_id} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                  <td className="font-medium text-zinc-100">{q.from_name}</td>
                  <td className="text-zinc-400">{q.subject}</td>
                  <td><Badge label={q.category.replace(/_/g, " ")} /></td>
                  <td className="num text-right text-zinc-400">{q.age_days}d</td>
                  <td><Confidence value={q.confidence} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel title="Workflow watch" aside={`${data.workflows.length} sequences · rewrites are proposed only`}>
        {data.workflows.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">No outbound sequences tracked yet.</p>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                  <th>Sequence</th><th className="text-right">Sent</th><th>Open rate</th>
                  <th>Reply rate</th><th className="text-right">Booked jobs</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.workflows.map((w) => (
                  <tr key={w.workflow_id} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                    <td className="font-medium text-zinc-100">{w.name}</td>
                    <td className="num text-right text-zinc-300">{w.emails_sent}</td>
                    <td>
                      <span className="num text-zinc-100">{pct(w.open_rate)}</span>
                      <RateDelta value={w.open_rate} benchmark={w.benchmark_open_rate} />
                      <div className="num mt-0.5 text-[10px] text-zinc-600">bench {pct(w.benchmark_open_rate)}</div>
                    </td>
                    <td>
                      <span className="num text-zinc-100">{pct(w.reply_rate)}</span>
                      <RateDelta value={w.reply_rate} benchmark={w.benchmark_reply_rate} />
                      <div className="num mt-0.5 text-[10px] text-zinc-600">bench {pct(w.benchmark_reply_rate)}</div>
                    </td>
                    <td className="num text-right font-medium text-emerald-300">{w.booked_jobs}</td>
                    <td><WorkflowStatus value={w.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {(rewrites.length > 0 || applied.length > 0) && (
              <div className="space-y-3 border-t border-white/[0.06] px-5 py-4">
                {applied.map(({ workflow, rewrite }) => (
                  <div
                    key={`applied-${workflow.workflow_id}`}
                    className="rounded-xl border border-emerald-400/25 bg-emerald-400/[0.06] px-4 py-3"
                  >
                    <div className="label mb-1.5 text-emerald-300">
                      applied rewrite · {workflow.name}
                    </div>
                    <div className="text-sm font-medium text-zinc-100">{rewrite.subject}</div>
                    <div className="mt-1 text-[13px] text-zinc-300">{rewrite.preview}</div>
                    <div className="mt-2 text-xs text-zinc-500">
                      applied by {rewrite.applied_by} — this copy is now live on the sequence
                    </div>
                  </div>
                ))}
                {rewrites
                  .filter(({ workflow }) => !workflow.applied_rewrite)
                  .map(({ workflow, rewrite }) => (
                  <div
                    key={workflow.workflow_id}
                    className="rounded-xl border border-amber-300/20 bg-amber-300/[0.05] px-4 py-3"
                  >
                    <div className="label mb-1.5">proposed rewrite · {workflow.name}</div>
                    <div className="text-sm font-medium text-zinc-100">{rewrite.subject}</div>
                    <div className="mt-1 text-[13px] text-zinc-300">{rewrite.preview}</div>
                    <div className="mt-2 text-xs text-zinc-500">{rewrite.rationale}</div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </Panel>

      <p className="text-xs text-zinc-600">
        The Email agent proposes; you approve. No reply is sent, no email deleted, and no sequence rewritten without an
        explicit approval.
      </p>
    </div>
  );
}
