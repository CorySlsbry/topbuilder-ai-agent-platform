"use client";

import { useCallback, useEffect, useState } from "react";

import { EmptyState, Panel, Spinner } from "@/components/ui";
import { ApiError, apiRequest } from "@/lib/api";
import type { Issue, IssuesPayload } from "@/lib/eos-types";

/** The L10 Issues list (IDS — Identify, Discuss, Solve) — the sticky Bloom Growth "communication hub"
 * value beyond the scorecard: open issues, owned + prioritized, that leadership works to resolution.
 * Add a new issue, resolve an open one; counts in the header. Leadership-only (a 403 → the leadership
 * EmptyState, same as the Executive view). Adds/resolves are gated server-side (admin + 2FA), so a
 * non-operator sees a clear, friendly message rather than a silent failure. Theme-aware throughout. */

// Mirrors /v1/org/overview department colors (same map the page + ExecutiveView use).
const DEPT_COLORS: Record<string, string> = {
  leadership: "#f59e0b",
  front_office: "#38bdf8",
  dispatch: "#a78bfa",
  field: "#34d399",
  sales: "#fb7185",
  finance: "#818cf8",
  warehouse: "#fb923c",
};

const DEPT_OPTIONS: { key: string; label: string }[] = [
  { key: "", label: "Company-wide" },
  { key: "leadership", label: "Leadership" },
  { key: "front_office", label: "Front Office" },
  { key: "dispatch", label: "Dispatch" },
  { key: "field", label: "Field Operations" },
  { key: "sales", label: "Sales" },
  { key: "finance", label: "Finance & Accounting" },
  { key: "warehouse", label: "Warehouse & Inventory" },
];

const PRIORITY_META: Record<number, { label: string; cls: string }> = {
  1: { label: "P1", cls: "text-red-300 bg-red-300/10 border-red-300/25" },
  2: { label: "P2", cls: "text-amber-300 bg-amber-300/10 border-amber-300/25" },
  3: { label: "P3", cls: "text-zinc-400 bg-white/5 border-white/10" },
};

const getIssues = (t: string) =>
  apiRequest<IssuesPayload>(t, "/v1/org/issues", "load the issues list");
const postIssue = (t: string, body: { title: string; owner: string; department: string; priority: number }) =>
  apiRequest<Issue>(t, "/v1/org/issues", "add this issue", { method: "POST", body: JSON.stringify(body) });
const postResolve = (t: string, id: string) =>
  apiRequest<Issue>(t, `/v1/org/issues/${id}/resolve`, "resolve this issue", { method: "POST" });

function DeptChip({ dept }: { dept: string }) {
  if (!dept) return <span className="text-[10px] uppercase tracking-wide text-zinc-500">Company-wide</span>;
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

function PriorityChip({ priority }: { priority: number }) {
  const meta = PRIORITY_META[priority] ?? PRIORITY_META[2];
  return (
    <span className={`inline-flex rounded-md border px-1.5 py-px text-[10px] font-semibold ${meta.cls}`}>
      {meta.label}
    </span>
  );
}

const fmtDate = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

export default function IssuesView({ token }: { token: string }) {
  const [data, setData] = useState<IssuesPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // add-issue form
  const [title, setTitle] = useState("");
  const [owner, setOwner] = useState("");
  const [department, setDepartment] = useState("");
  const [priority, setPriority] = useState(2);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [resolving, setResolving] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setForbidden(false);
    try {
      setData(await getIssues(token));
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) setForbidden(true);
      else setError(e instanceof Error ? e.message : "Couldn't load the issues list.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || submitting) return;
    setSubmitting(true);
    setFormError(null);
    try {
      await postIssue(token, { title: title.trim(), owner: owner.trim(), department, priority });
      setTitle("");
      setOwner("");
      setDepartment("");
      setPriority(2);
      await load();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Couldn't add the issue.");
    } finally {
      setSubmitting(false);
    }
  }

  async function resolve(id: string) {
    if (resolving) return;
    setResolving(id);
    setFormError(null);
    try {
      await postResolve(token, id);
      await load();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Couldn't resolve the issue.");
    } finally {
      setResolving(null);
    }
  }

  if (loading && !data) {
    return (
      <div className="panel grid place-items-center px-6 py-20 text-zinc-500">
        <Spinner />
        <span className="mt-3 text-sm">Loading the issues list…</span>
      </div>
    );
  }

  if (forbidden) {
    return (
      <EmptyState
        title="The issues list is available to leadership accounts"
        body="The L10 issues list is your team's shared 'what needs solving' — ask an owner or executive to share what you need."
        busy={loading}
        onRun={() => void load()}
      />
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
        {error ?? "Could not load the issues list."}
        <button className="ml-3 underline underline-offset-2" onClick={() => void load()}>Retry</button>
      </div>
    );
  }

  const open = data.issues.filter((i) => i.status === "open");
  const closed = data.issues.filter((i) => i.status === "closed");
  const s = data.summary;

  return (
    <div className="space-y-4">
      {/* ---- header summary chips ---- */}
      <div className="panel flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-5 py-3.5">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">Issues (L10 — Identify · Discuss · Solve)</h2>
          <p className="mt-0.5 text-xs text-zinc-500">
            The shared list of what needs solving — owned, prioritized, worked to resolution. The sticky
            Bloom value beyond the scorecard.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="rounded-md border border-amber-500/25 bg-amber-500/10 px-2 py-1 font-medium text-amber-200">
            {s.open} open
          </span>
          <span className="rounded-md border border-white/10 bg-white/[0.03] px-2 py-1 text-zinc-400">
            {s.closed} closed
          </span>
          <span className="rounded-md border border-red-400/25 bg-red-400/10 px-2 py-1 font-medium text-red-300">
            P1: {s.open_by_priority["1"] ?? 0}
          </span>
        </div>
      </div>

      {/* ---- add issue ---- */}
      <Panel title="Add an issue">
        <form className="flex flex-col gap-3 p-4 lg:flex-row lg:items-end" onSubmit={add}>
          <label className="min-w-0 flex-1">
            <span className="label">Issue</span>
            <input
              className="field mt-1"
              placeholder="What needs solving?"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
            />
          </label>
          <label className="lg:w-40">
            <span className="label">Owner</span>
            <input
              className="field mt-1"
              placeholder="Who owns it?"
              value={owner}
              onChange={(e) => setOwner(e.target.value)}
            />
          </label>
          <label className="lg:w-44">
            <span className="label">Department</span>
            <select className="field mt-1" value={department} onChange={(e) => setDepartment(e.target.value)}>
              {DEPT_OPTIONS.map((d) => (
                <option key={d.key} value={d.key}>{d.label}</option>
              ))}
            </select>
          </label>
          <label className="lg:w-28">
            <span className="label">Priority</span>
            <select
              className="field mt-1"
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
            >
              <option value={1}>P1 — High</option>
              <option value={2}>P2 — Medium</option>
              <option value={3}>P3 — Low</option>
            </select>
          </label>
          <button className="btn-primary lg:shrink-0" type="submit" disabled={submitting || !title.trim()}>
            {submitting ? <Spinner /> : null}
            {submitting ? "Adding…" : "Add issue"}
          </button>
        </form>
        {formError && (
          <div className="mx-4 mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
            {formError}
          </div>
        )}
      </Panel>

      {/* ---- open issues ---- */}
      <Panel title="Open issues" aside={`${open.length} to solve`}>
        {open.length === 0 ? (
          <div className="px-5 py-10 text-center text-sm text-zinc-500">
            No open issues — the list is clear. Add one above as it comes up.
          </div>
        ) : (
          <ul className="divide-y divide-white/[0.05]">
            {open.map((i) => (
              <li key={i.id} className="flex items-start gap-3 px-5 py-3.5">
                <div className="mt-0.5 shrink-0">
                  <PriorityChip priority={i.priority} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-zinc-100">{i.title}</div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                    <span className="text-zinc-400">{i.owner}</span>
                    <span aria-hidden>·</span>
                    <DeptChip dept={i.department} />
                    <span aria-hidden>·</span>
                    <span>opened {fmtDate(i.created)}</span>
                  </div>
                </div>
                <button
                  className="btn-ghost shrink-0 text-xs"
                  onClick={() => void resolve(i.id)}
                  disabled={resolving === i.id}
                  title="Mark this issue solved"
                >
                  {resolving === i.id ? <Spinner /> : "✓"}
                  {resolving === i.id ? "Resolving…" : "Resolve"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {/* ---- recently solved ---- */}
      {closed.length > 0 && (
        <Panel title="Recently solved" aside={`${closed.length}`}>
          <ul className="divide-y divide-white/[0.05]">
            {closed.map((i) => (
              <li key={i.id} className="flex items-center gap-3 px-5 py-3 text-sm">
                <span className="shrink-0 text-emerald-400" aria-hidden>✓</span>
                <span className="min-w-0 flex-1 truncate text-zinc-400 line-through decoration-zinc-600">
                  {i.title}
                </span>
                <span className="shrink-0 text-xs text-zinc-600">solved {fmtDate(i.resolved)}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}
