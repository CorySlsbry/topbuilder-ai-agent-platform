"use client";

import { useCallback, useEffect, useState } from "react";

import DepartmentSection from "@/components/DepartmentSection";
import { EmptyState, Spinner } from "@/components/ui";
import { ApiError, getScorecard } from "@/lib/api";
import type { KpiDef, Scorecard } from "@/lib/types";

/** The auto-computed Department Scorecard — the proper replacement for the manual Bloom Growth L10
 * scorecard (3-4 people keying it weekly). Four department sections, each visually separated, with a
 * persistent per-department KPI selector + per-rep/tech side-by-side panels.
 *
 * Lazy-fetches /v1/org/scorecard; leadership-only (a 403 → the leadership EmptyState, same as the
 * Executive view). It powers ExecutiveView's "By Department" tab. */
export default function ScorecardView({ token }: { token: string }) {
  const [data, setData] = useState<Scorecard | null>(null);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setForbidden(false);
    try {
      setData(await getScorecard(token, { weeks: 13 }));
    } catch (e) {
      // A 403 means a department-scoped principal — show the leadership EmptyState, not an error.
      if (e instanceof ApiError && e.status === 403) setForbidden(true);
      else setError(e instanceof Error ? e.message : "Couldn't load the scorecard.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !data) {
    return (
      <div className="panel grid place-items-center px-6 py-20 text-zinc-500">
        <Spinner />
        <span className="mt-3 text-sm">Loading the department scorecard…</span>
      </div>
    );
  }

  if (forbidden) {
    return (
      <EmptyState
        title="The scorecard is available to leadership accounts"
        body="It rolls up every department's KPIs across the whole company — ask an owner or executive to share what you need."
        busy={loading}
        onRun={() => void load()}
      />
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
        {error ?? "Could not load the scorecard."}
        <button className="ml-3 underline underline-offset-2" onClick={() => void load()}>
          Retry
        </button>
      </div>
    );
  }

  if (data.departments.length === 0) {
    return (
      <div className="panel px-6 py-16 text-center text-sm text-zinc-500">
        No departments to score yet — connect ServiceTitan and QuickBooks and the scorecard fills in
        automatically.
        <div className="mt-2 text-xs text-zinc-600">This is what replaces hand-keying Bloom Growth every week.</div>
      </div>
    );
  }

  // The catalog is the single source of truth the selector reads (every KPI per department, incl.
  // calculated ones) — index it once and hand each section only its own entries.
  const catalogByDept = new Map<string, KpiDef[]>();
  for (const def of data.catalog) {
    const list = catalogByDept.get(def.department) ?? [];
    list.push(def);
    catalogByDept.set(def.department, list);
  }

  return (
    <div className="space-y-4">
      <div className="panel flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-5 py-3.5">
        <h2 className="text-sm font-semibold text-zinc-100">Department Scorecard</h2>
        <span className="text-xs text-zinc-500">
          Auto-computed from ServiceTitan + QuickBooks · {data.period_weeks}-week history · goal vs actual,
          with the per-rep trend Bloom can&apos;t show
        </span>
      </div>

      {data.departments.map((dept) => (
        <DepartmentSection key={dept.key} department={dept} catalog={catalogByDept.get(dept.key) ?? []} />
      ))}
    </div>
  );
}
