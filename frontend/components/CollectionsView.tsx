"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import { Kpi, Panel, Spinner, usd } from "@/components/ui";
import {
  getAgentPolicy,
  getCollections,
  proposeDunning,
  runCollections,
} from "@/lib/api";
import type {
  AgentMode,
  CollectionsRunResult,
  WorklistCustomer,
} from "@/lib/types";

// --------------------------------------------------------------------------------------------
// Aging buckets + workflow status — mirrors backend/app/agents/collections/analytics.py exactly.
// Bucket chips are color-coded by AGE (cool → hot) so the eye lands on the oldest money first.
// --------------------------------------------------------------------------------------------
const BUCKET_ORDER = ["current", "1-30", "31-60", "61-90", "91-120", "121+"] as const;
type Bucket = (typeof BUCKET_ORDER)[number];

const BUCKET_LABEL: Record<Bucket, string> = {
  current: "Current",
  "1-30": "1–30",
  "31-60": "31–60",
  "61-90": "61–90",
  "91-120": "91–120",
  "121+": "121+",
};

// Each chip carries its own text/bg/border so it reads on BOTH the dark and the light theme
// (colors chosen with enough contrast for the .light pass to keep them legible).
const BUCKET_CHIP: Record<Bucket, string> = {
  current: "text-emerald-300 bg-emerald-400/10 border-emerald-400/25",
  "1-30": "text-sky-300 bg-sky-400/10 border-sky-400/25",
  "31-60": "text-amber-300 bg-amber-400/10 border-amber-400/25",
  "61-90": "text-orange-300 bg-orange-400/10 border-orange-400/25",
  "91-120": "text-rose-300 bg-rose-400/10 border-rose-400/25",
  "121+": "text-red-300 bg-red-500/15 border-red-500/30",
};

const STATUS_META: Record<string, { label: string; cls: string }> = {
  reconciled: { label: "Reconciled", cls: "text-emerald-300 bg-emerald-400/10 border-emerald-400/25" },
  expecting_money: { label: "Expecting money", cls: "text-sky-300 bg-sky-400/10 border-sky-400/25" },
  stalled_our_court: { label: "Our court", cls: "text-amber-300 bg-amber-400/10 border-amber-400/25" },
  stalled_other_court: { label: "Their court", cls: "text-violet-300 bg-violet-400/10 border-violet-400/25" },
  action_required: { label: "Action required", cls: "text-orange-300 bg-orange-400/10 border-orange-400/25" },
  write_off_or_collections: { label: "Write-off / collections", cls: "text-red-300 bg-red-500/15 border-red-500/30" },
};

const CHANNEL_ICON: Record<string, string> = { email: "✉️", sms: "💬", call: "📞", none: "—" };

// Filter dropdowns share these option lists (status only over statuses that actually appear).
const ALL = "all";

function Chip({ children, cls }: { children: ReactNode; cls: string }) {
  return (
    <span className={`inline-flex shrink-0 rounded-md border px-2 py-0.5 text-[11px] font-medium ${cls}`}>
      {children}
    </span>
  );
}

function BucketChip({ bucket }: { bucket: string }) {
  const b = (BUCKET_ORDER.includes(bucket as Bucket) ? bucket : "current") as Bucket;
  return <Chip cls={BUCKET_CHIP[b]}>{BUCKET_LABEL[b]}</Chip>;
}

function StatusChip({ status }: { status: string }) {
  const m = STATUS_META[status] ?? { label: status.replace(/_/g, " "), cls: "text-zinc-300 bg-white/5 border-white/10" };
  return <Chip cls={m.cls}>{m.label}</Chip>;
}

// A horizontal aging ladder: the portfolio split across buckets as proportional segments.
function AgingLadder({ buckets, total }: { buckets: Record<string, number>; total: number }) {
  if (total <= 0) return <div className="text-xs text-zinc-500">No open balance.</div>;
  const SEG: Record<Bucket, string> = {
    current: "bg-emerald-400/70",
    "1-30": "bg-sky-400/70",
    "31-60": "bg-amber-400/70",
    "61-90": "bg-orange-400/70",
    "91-120": "bg-rose-400/70",
    "121+": "bg-red-500/80",
  };
  return (
    <div>
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-white/5">
        {BUCKET_ORDER.map((b) => {
          const v = buckets[b] ?? 0;
          const pct = (v / total) * 100;
          return pct > 0 ? (
            <div key={b} className={SEG[b]} style={{ width: `${pct}%` }} title={`${BUCKET_LABEL[b]}: ${usd(v)}`} />
          ) : null;
        })}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {BUCKET_ORDER.map((b) => {
          const v = buckets[b] ?? 0;
          return v > 0 ? (
            <span key={b} className="flex items-center gap-1.5 text-[11px] text-zinc-400">
              <span className={`inline-block h-2 w-2 rounded-sm ${SEG[b]}`} />
              {BUCKET_LABEL[b]} <span className="num text-zinc-300">{usd(v)}</span>
            </span>
          ) : null;
        })}
      </div>
    </div>
  );
}

type SortKey = "age" | "balance";

export default function CollectionsView({ token }: { token: string }) {
  const [data, setData] = useState<CollectionsRunResult | null>(null);
  const [mode, setMode] = useState<AgentMode>("hitl");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  // table controls
  const [bucketFilter, setBucketFilter] = useState<string>(ALL);
  const [statusFilter, setStatusFilter] = useState<string>(ALL);
  const [sortKey, setSortKey] = useState<SortKey>("age");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  // Locally-captured promises (the API has no promise-write route yet — see report). Keyed by
  // customer_id; the next agent run, fed real promises, will reflect them server-side.
  const [promises, setPromises] = useState<Record<string, { date: string; amount: string }>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [d, p] = await Promise.all([
        getCollections(token),
        getAgentPolicy(token, "collections").catch(() => null),
      ]);
      setData(d);
      if (p) setMode(p.mode);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load collections — try again.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onRun() {
    setLoading(true);
    setError(null);
    setNote(null);
    try {
      setData(await runCollections(token));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't run the collections agent — try again.");
    } finally {
      setLoading(false);
    }
  }

  async function sendDunning(c: WorklistCustomer) {
    if (!data?.run_id) return;
    setBusyId(c.customer_id);
    setNote(null);
    setError(null);
    try {
      const action = await proposeDunning(token, data.run_id, c.customer_id);
      const verb = { email: "Emailed", sms: "Texted", call: "Called" }[c.dunning_channel] ?? "Contacted";
      if (action.status === "executed") {
        setNote(`${verb} ${c.customer_name} — ${c.dunning_step === 5 ? "final" : "step " + c.dunning_step} dunning sent.`);
      } else {
        setNote(
          `Queued the ${c.dunning_channel} dunning for ${c.customer_name} — it's awaiting an operator's approval under Agent Controls.`,
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send that dunning step — try again.");
    } finally {
      setBusyId(null);
    }
  }

  function capturePromise(c: WorklistCustomer, date: string, amount: string) {
    if (!date) return;
    setPromises((p) => ({ ...p, [c.customer_id]: { date, amount } }));
    setNote(
      `Logged a promise-to-pay from ${c.customer_name} for ${date}. It parks them in "Expecting money" — run the agent again to re-prioritize the worklist.`,
    );
  }

  const statusOptions = useMemo(() => {
    const set = new Set<string>();
    (data?.worklist ?? []).forEach((c) => set.add(c.status));
    return Array.from(set);
  }, [data]);

  const rows = useMemo(() => {
    let list = data?.worklist ?? [];
    if (bucketFilter !== ALL) list = list.filter((c) => c.bucket === bucketFilter);
    if (statusFilter !== ALL) list = list.filter((c) => c.status === statusFilter);
    const sorted = [...list].sort((a, b) =>
      sortKey === "balance"
        ? b.balance_usd - a.balance_usd
        : b.oldest_days_overdue - a.oldest_days_overdue || b.balance_usd - a.balance_usd,
    );
    return sorted;
  }, [data, bucketFilter, statusFilter, sortKey]);

  if (loading && !data) {
    return (
      <div className="panel grid place-items-center px-6 py-16 text-zinc-500">
        <Spinner />
        <span className="mt-3 text-sm">Loading collections…</span>
      </div>
    );
  }

  // No persisted run yet → friendly empty state with a run button.
  if (!data) {
    return (
      <div className="space-y-4">
        {error && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-200">
            {error}
            <button className="ml-3 underline underline-offset-2" onClick={() => void load()}>Retry</button>
          </div>
        )}
        <div className="panel grid place-items-center px-6 py-16 text-center">
          <h2 className="text-lg font-semibold text-zinc-100">No collections run yet</h2>
          <p className="mt-1 max-w-md text-sm text-zinc-500">
            Build the A/R worklist from your open invoices — aging buckets, who owes, and the next dunning step for each.
          </p>
          <button className="btn-primary mt-5" onClick={onRun} disabled={loading}>
            {loading ? <Spinner /> : null}
            {loading ? "Analyzing…" : "Run collections"}
          </button>
        </div>
      </div>
    );
  }

  const t = data.totals;
  const open = t.open_balance_usd;

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-200">
          {error}
          <button className="ml-3 underline underline-offset-2" onClick={() => void load()}>Retry</button>
        </div>
      )}
      {note && <div className="rounded-xl border border-accent/30 bg-accent/10 px-4 py-2.5 text-sm text-accent-soft">{note}</div>}

      {/* Portfolio header — the Outstanding-A/R sheet at a glance. */}
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Kpi label="Open A/R" value={usd(open)} tone="neutral" />
        <Kpi label="Overdue" value={usd(t.overdue_balance_usd)} tone="warn" />
        <Kpi label="% current" value={`${t.pct_current.toFixed(0)}%`} tone={t.pct_current >= 80 ? "ok" : "warn"} />
        <Kpi label="% over 30" value={`${t.pct_over_30.toFixed(0)}%`} tone={t.pct_over_30 >= 20 ? "bad" : "neutral"} />
        <Kpi label="91+ at risk" value={usd(t.at_risk_balance_usd)} tone={t.at_risk_balance_usd > 0 ? "bad" : "ok"} />
      </section>

      <Panel
        title="Portfolio aging"
        aside={`${t.customers} customers · ${t.customers_needing_action} need action`}
      >
        <div className="px-5 py-4">
          <AgingLadder buckets={t.bucket_balances_usd} total={open} />
        </div>
      </Panel>

      {/* The worklist — sortable + filterable. */}
      <Panel
        title="Collections worklist"
        aside={
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={bucketFilter}
              onChange={(e) => setBucketFilter(e.target.value)}
              className="rounded-md border border-white/10 bg-transparent px-2 py-1 text-xs text-zinc-300"
              aria-label="Filter by aging bucket"
            >
              <option value={ALL}>All buckets</option>
              {BUCKET_ORDER.map((b) => (
                <option key={b} value={b}>{BUCKET_LABEL[b]}</option>
              ))}
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="rounded-md border border-white/10 bg-transparent px-2 py-1 text-xs text-zinc-300"
              aria-label="Filter by status"
            >
              <option value={ALL}>All statuses</option>
              {statusOptions.map((s) => (
                <option key={s} value={s}>{STATUS_META[s]?.label ?? s.replace(/_/g, " ")}</option>
              ))}
            </select>
            <select
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value as SortKey)}
              className="rounded-md border border-white/10 bg-transparent px-2 py-1 text-xs text-zinc-300"
              aria-label="Sort"
            >
              <option value="age">Oldest first</option>
              <option value="balance">Largest balance</option>
            </select>
          </div>
        }
      >
        {rows.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-zinc-500">
            {(data.worklist?.length ?? 0) === 0
              ? "No open A/R — everyone is reconciled. 🎉"
              : "No customers match these filters."}
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                <th>Customer</th>
                <th className="text-right">Balance</th>
                <th>Aging</th>
                <th className="text-right">Days</th>
                <th>Status</th>
                <th>Owner</th>
                <th>Next action</th>
                <th className="text-right">Promise</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => {
                const isOpen = expanded === c.customer_id;
                const localPromise = promises[c.customer_id];
                const promiseDate = localPromise?.date ?? c.promise_date;
                const promiseAmt =
                  localPromise?.amount && localPromise.amount !== ""
                    ? Number(localPromise.amount)
                    : c.promise_amount_usd;
                const canSend = c.dunning_step > 0 && c.dunning_channel !== "none" && c.oldest_days_overdue > 0;
                return (
                  <CustomerRow
                    key={c.customer_id}
                    c={c}
                    isOpen={isOpen}
                    onToggle={() => setExpanded(isOpen ? null : c.customer_id)}
                    promiseDate={promiseDate}
                    promiseAmt={promiseAmt ?? null}
                    canSend={canSend}
                    sendDisabled={mode === "off"}
                    busy={busyId === c.customer_id}
                    onSend={() => void sendDunning(c)}
                    onCapturePromise={(d, a) => capturePromise(c, d, a)}
                  />
                );
              })}
            </tbody>
          </table>
        )}
      </Panel>

      <footer className="flex flex-wrap items-center justify-between gap-2 pt-1 text-xs text-zinc-600">
        <span className="num">
          {data.run_id ? `run ${data.run_id.slice(0, 8)} · ` : ""}inputs {data.inputs_hash.slice(0, 12)} · A/R from {data.source_system}
        </span>
        <span>
          {mode === "off"
            ? "Collections agent is off — turn it on under Agent Controls to send dunning."
            : mode === "auto"
              ? "Auto mode — Approve & send executes immediately."
              : "Advisory — Top Builder AI drafts; you approve & send."}
        </span>
      </footer>
    </div>
  );
}

// --------------------------------------------------------------------------------------------
// One worklist row + its expandable drawer (drafted email/SMS/call + promise capture).
// --------------------------------------------------------------------------------------------
function CustomerRow({
  c,
  isOpen,
  onToggle,
  promiseDate,
  promiseAmt,
  canSend,
  sendDisabled,
  busy,
  onSend,
  onCapturePromise,
}: {
  c: WorklistCustomer;
  isOpen: boolean;
  onToggle: () => void;
  promiseDate: string | null;
  promiseAmt: number | null;
  canSend: boolean;
  sendDisabled: boolean;
  busy: boolean;
  onSend: () => void;
  onCapturePromise: (date: string, amount: string) => void;
}) {
  return (
    <>
      <tr
        className="cursor-pointer border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02] [&>td]:px-5 [&>td]:py-3"
        onClick={onToggle}
      >
        <td className="font-medium text-zinc-100">
          <span className="mr-1.5 inline-block w-2 text-zinc-500">{isOpen ? "▾" : "▸"}</span>
          {c.customer_name}
          <span className="ml-2 text-[11px] capitalize text-zinc-500">{c.customer_segment}</span>
        </td>
        <td className="num text-right font-medium text-zinc-100">{usd(c.balance_usd)}</td>
        <td><BucketChip bucket={c.bucket} /></td>
        <td className="num text-right text-zinc-400">{c.oldest_days_overdue > 0 ? c.oldest_days_overdue : "—"}</td>
        <td><StatusChip status={c.status} /></td>
        <td className="text-zinc-400">{c.owner}</td>
        <td className="max-w-[240px] truncate text-[13px] text-zinc-400" title={c.next_action}>{c.next_action}</td>
        <td className="num text-right text-zinc-400">
          {promiseDate ? (
            <span className="text-sky-300">
              {promiseDate}
              {promiseAmt != null ? <span className="ml-1 text-zinc-500">{usd(promiseAmt)}</span> : null}
            </span>
          ) : (
            "—"
          )}
        </td>
        <td className="text-right" onClick={(e) => e.stopPropagation()}>
          {canSend ? (
            <button
              className="btn-primary !px-3 !py-1 text-xs"
              disabled={busy || sendDisabled}
              title={sendDisabled ? "Collections agent is off (Agent Controls)" : `Send the ${c.dunning_channel} dunning step`}
              onClick={onSend}
            >
              {busy ? "Sending…" : `${CHANNEL_ICON[c.dunning_channel] ?? ""} Approve & send`}
            </button>
          ) : (
            <span className="text-[11px] text-zinc-600">no action</span>
          )}
        </td>
      </tr>
      {isOpen && (
        <tr className="border-b border-white/[0.04] bg-black/10">
          <td colSpan={9} className="px-5 py-4">
            <DunningDrawer c={c} onCapturePromise={onCapturePromise} />
          </td>
        </tr>
      )}
    </>
  );
}

function DunningDrawer({
  c,
  onCapturePromise,
}: {
  c: WorklistCustomer;
  onCapturePromise: (date: string, amount: string) => void;
}) {
  const d = c.drafts;
  const [pDate, setPDate] = useState("");
  const [pAmount, setPAmount] = useState("");

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
      {/* Invoices that make up the balance. */}
      <div className="lg:col-span-1">
        <div className="label mb-2">Open invoices ({c.invoices.length})</div>
        <ul className="space-y-1.5">
          {c.invoices.map((inv) => (
            <li key={inv.invoice_id} className="flex items-center justify-between gap-2 text-[13px]">
              <span className="truncate text-zinc-300">#{inv.doc_number ?? inv.invoice_id}</span>
              <span className="flex shrink-0 items-center gap-2">
                <BucketChip bucket={inv.bucket} />
                <span className="num text-zinc-200">{usd(inv.balance_usd)}</span>
              </span>
            </li>
          ))}
        </ul>

        {/* Promise-to-pay capture. */}
        <div className="mt-4 rounded-lg border border-white/[0.06] p-3">
          <div className="label mb-2">Log a promise-to-pay</div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-[11px] text-zinc-500">
              Date
              <input
                type="date"
                value={pDate}
                onChange={(e) => setPDate(e.target.value)}
                className="rounded-md border border-white/10 bg-transparent px-2 py-1 text-xs text-zinc-200"
              />
            </label>
            <label className="flex flex-col gap-1 text-[11px] text-zinc-500">
              Amount (optional)
              <input
                type="number"
                inputMode="decimal"
                placeholder={String(Math.round(c.balance_usd))}
                value={pAmount}
                onChange={(e) => setPAmount(e.target.value)}
                className="w-28 rounded-md border border-white/10 bg-transparent px-2 py-1 text-xs text-zinc-200"
              />
            </label>
            <button
              className="btn-ghost !px-3 !py-1 text-xs"
              disabled={!pDate}
              onClick={() => onCapturePromise(pDate, pAmount)}
            >
              Log promise
            </button>
          </div>
        </div>
      </div>

      {/* The drafted outreach for the recommended step. */}
      <div className="lg:col-span-2">
        <div className="mb-2 flex items-center gap-2">
          <span className="label">
            Recommended: step {c.dunning_step} · {c.dunning_channel}
          </span>
        </div>
        {c.dunning_channel === "none" || c.dunning_step === 0 ? (
          <p className="rounded-lg border border-amber-500/20 bg-amber-500/[0.06] px-3 py-2.5 text-[13px] text-amber-200">
            No compliant outreach channel — mail a statement or assign a human.
          </p>
        ) : (
          <div className="space-y-3">
            {(c.dunning_channel === "email" || d.email_body) && d.email_body && (
              <DraftBlock title="✉️ Email" subject={d.email_subject} body={d.email_body} />
            )}
            {(c.dunning_channel === "sms" || d.sms_body) && d.sms_body && (
              <DraftBlock title="💬 SMS" body={d.sms_body} />
            )}
            {(c.dunning_channel === "call" || d.call_script) && d.call_script && (
              <DraftBlock title="📞 Call script" body={d.call_script} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function DraftBlock({ title, subject, body }: { title: string; subject?: string | null; body: string }) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="label">{title}</span>
        {subject ? <span className="truncate text-[12px] font-medium text-zinc-300">{subject}</span> : null}
      </div>
      <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-300">{body}</p>
    </div>
  );
}
