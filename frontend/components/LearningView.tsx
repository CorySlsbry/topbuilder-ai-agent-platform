"use client";

import { useCallback, useEffect, useState } from "react";

import {
  approvePreference,
  listDrift,
  listPreferences,
  rejectPreference,
  retirePreference,
  runConsolidation,
  type DriftSnapshot,
  type Preference,
} from "@/lib/api";

const AGENTS = ["all", "workforce", "financial", "inventory", "booking", "routing", "documents"] as const;

export default function LearningView({ token }: { token: string }) {
  const [agent, setAgent] = useState<(typeof AGENTS)[number]>("all");
  const [candidates, setCandidates] = useState<Preference[]>([]);
  const [actives, setActives] = useState<Preference[]>([]);
  const [drift, setDrift] = useState<DriftSnapshot[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const scope = agent === "all" ? undefined : agent;

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [cand, act, dr] = await Promise.all([
        listPreferences(token, scope, "candidate"),
        listPreferences(token, scope, "active"),
        listDrift(token, scope),
      ]);
      setCandidates(cand);
      setActives(act);
      // keep only the most recent drift snapshot per agent
      const latest = new Map<string, DriftSnapshot>();
      for (const d of dr) if (!latest.has(d.agent)) latest.set(d.agent, d);
      setDrift([...latest.values()]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }, [token, scope]);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(id: string, fn: () => Promise<unknown>, ok: string) {
    setBusyId(id);
    setMsg(null);
    setErr(null);
    try {
      await fn();
      setMsg(ok);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusyId(null);
    }
  }

  async function consolidate() {
    setLoading(true);
    setMsg(null);
    setErr(null);
    try {
      await runConsolidation(token, scope);
      setMsg("Consolidation run complete — candidates re-evaluated, drift snapshot taken.");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Consolidation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={agent}
          onChange={(e) => setAgent(e.target.value as (typeof AGENTS)[number])}
          className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-200"
        >
          {AGENTS.map((a) => (
            <option key={a} value={a}>{a === "all" ? "All agents" : a}</option>
          ))}
        </select>
        <button
          onClick={consolidate}
          disabled={loading}
          className="rounded-lg border border-indigo-500/40 bg-indigo-500/10 px-3 py-1.5 text-sm text-indigo-200 hover:bg-indigo-500/20 disabled:opacity-50"
        >
          Run consolidation
        </button>
        <button
          onClick={() => void load()}
          disabled={loading}
          className="rounded-lg border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
        >
          Refresh
        </button>
        <span className="text-xs text-zinc-500">
          A learned rule only reaches narration after it clears the eval gate + your approval, then rolls out behind a canary %.
        </span>
      </div>

      {msg && <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-2.5 text-sm text-emerald-200">{msg}</div>}
      {err && <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-200">{err}</div>}

      {/* Drift monitor */}
      <section className="panel p-4">
        <h2 className="mb-3 text-sm font-semibold text-zinc-200">Agent health (drift monitor)</h2>
        {drift.length === 0 ? (
          <p className="text-sm text-zinc-500">No drift snapshots yet — run a consolidation to take one.</p>
        ) : (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {drift.map((d) => (
              <div key={d.id} className={`rounded-lg border px-3 py-2 ${d.flagged ? "border-amber-500/40 bg-amber-500/10" : "border-zinc-700 bg-zinc-900"}`}>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-zinc-200">{d.agent}</span>
                  {d.flagged && <span className="text-xs text-amber-300">⚠ flagged</span>}
                </div>
                <div className="num mt-1 text-xs text-zinc-400">
                  n={d.sample_size} · edit {pct(d.edit_rate)} · reject {pct(d.reject_rate)} · eff {fix(d.avg_effectiveness)}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Approval queue */}
      <section className="panel p-4">
        <h2 className="mb-3 text-sm font-semibold text-zinc-200">
          Candidates awaiting approval <span className="text-zinc-500">({candidates.length})</span>
        </h2>
        {candidates.length === 0 ? (
          <p className="text-sm text-zinc-500">Nothing in the queue. Quorum-reached rules land here for review.</p>
        ) : (
          <ul className="space-y-2">
            {candidates.map((p) => (
              <li key={p.id} className="rounded-lg border border-zinc-700 bg-zinc-900 p-3">
                <p className="text-sm text-zinc-100">{p.preference_text}</p>
                <div className="num mt-1 text-xs text-zinc-500">
                  {p.agent} · support {p.support_count} · via {p.proposed_by}
                  {p.eval_score != null && <> · eval {fix(p.eval_score)}</>}
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    onClick={() => void act(p.id, () => approvePreference(token, p.id, 20), "Approved — live to a 20% canary.")}
                    disabled={busyId === p.id}
                    className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50"
                  >
                    Approve · canary 20%
                  </button>
                  <button
                    onClick={() => void act(p.id, () => approvePreference(token, p.id, 100), "Approved — live to 100%.")}
                    disabled={busyId === p.id}
                    className="rounded-md border border-emerald-500/30 px-2.5 py-1 text-xs text-emerald-300 hover:bg-emerald-500/10 disabled:opacity-50"
                  >
                    Approve · 100%
                  </button>
                  <button
                    onClick={() => void act(p.id, () => approvePreference(token, p.id, 20, true), "Force-approved (eval gate overridden).")}
                    disabled={busyId === p.id}
                    className="rounded-md border border-amber-500/30 px-2.5 py-1 text-xs text-amber-300 hover:bg-amber-500/10 disabled:opacity-50"
                  >
                    Force
                  </button>
                  <button
                    onClick={() => void act(p.id, () => rejectPreference(token, p.id), "Rejected.")}
                    disabled={busyId === p.id}
                    className="rounded-md border border-red-500/30 px-2.5 py-1 text-xs text-red-300 hover:bg-red-500/10 disabled:opacity-50"
                  >
                    Reject
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Active rules */}
      <section className="panel p-4">
        <h2 className="mb-3 text-sm font-semibold text-zinc-200">
          Active learned rules <span className="text-zinc-500">({actives.length})</span>
        </h2>
        {actives.length === 0 ? (
          <p className="text-sm text-zinc-500">No active rules yet — approved candidates appear here.</p>
        ) : (
          <ul className="space-y-2">
            {actives.map((p) => (
              <li key={p.id} className="flex items-start justify-between gap-3 rounded-lg border border-zinc-700 bg-zinc-900 p-3">
                <div>
                  <p className="text-sm text-zinc-100">{p.preference_text}</p>
                  <div className="num mt-1 text-xs text-zinc-500">{p.agent} · rollout {p.rollout_pct}% · support {p.support_count}</div>
                </div>
                <button
                  onClick={() => void act(p.id, () => retirePreference(token, p.id), "Retired.")}
                  disabled={busyId === p.id}
                  className="shrink-0 rounded-md border border-zinc-600 px-2.5 py-1 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
                >
                  Retire
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const fix = (v: number | null) => (v == null ? "—" : v.toFixed(2));
