"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import KpiSelector, { useVisibleKpis } from "@/components/KpiSelector";
import { KpiTrendsChart } from "@/components/KpiTrendChart";
import { FALLBACK_COLOR } from "@/components/chartKit";
import { fmtScorecardValue } from "@/components/DepartmentSection";
import { EmptyState, Spinner } from "@/components/ui";
import { ApiError, getScorecardTrends } from "@/lib/api";
import type { KpiDef, ScorecardTrends, TrendDepartment, TrendKpi } from "@/lib/types";

/** Rolling-year KPI trends with a deterministic seasonal forecast band — the exec "where is this
 * heading" view. Leadership/operator only (a 403 → the leadership EmptyState, same as ScorecardView).
 * Self-loads /v1/org/scorecard/trends; a department tab + weekly/monthly toggle + the shared
 * KpiSelector drive which KPIs render as full forecast-aware charts. */

// Per-department accent — matches the scorecard's DEPT_ACCENT so the two views read as one system.
const DEPT_ACCENT: Record<string, string> = {
  sales: "#fb7185",
  operations: "#34d399",
  sales_marketing: "#38bdf8",
  finance: "#818cf8",
};

// A sensible CFO/exec default-visible set per department (the rest stay one click away in the
// selector). Keys that a department doesn't actually return are filtered out at render time.
const DEFAULT_VISIBLE: Record<string, string[]> = {
  finance: ["cash", "cash_collected", "ar_total", "ar_pct_over_30", "quick_ratio", "margin_leakage"],
  sales: ["gross_sales", "closing_pct"],
  operations: ["completed_revenue_service", "utilization"],
  sales_marketing: ["book_rate", "after_hours_recovered"],
};

const WEEKS = 52;
const FORECAST_WEEKS = 26;

type Granularity = "weekly" | "monthly";

export default function KpiTrendsView({ token }: { token: string }) {
  const [data, setData] = useState<ScorecardTrends | null>(null);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeDept, setActiveDept] = useState<string | null>(null);
  const [granularity, setGranularity] = useState<Granularity>("weekly");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setForbidden(false);
    try {
      setData(await getScorecardTrends(token, { weeks: WEEKS, forecastWeeks: FORECAST_WEEKS }));
    } catch (e) {
      // A 403 means a department-scoped principal — show the leadership EmptyState, not an error.
      if (e instanceof ApiError && e.status === 403) setForbidden(true);
      else setError(e instanceof Error ? e.message : "Couldn't load the KPI trends.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  // Keep the active department valid as data arrives (first department by default).
  useEffect(() => {
    if (!data) return;
    setActiveDept((cur) =>
      cur && data.departments.some((d) => d.key === cur) ? cur : (data.departments[0]?.key ?? null),
    );
  }, [data]);

  if (loading && !data) {
    return (
      <div className="panel grid place-items-center px-6 py-20 text-zinc-500">
        <Spinner />
        <span className="mt-3 text-sm">Loading the KPI trends…</span>
      </div>
    );
  }

  if (forbidden) {
    return (
      <EmptyState
        title="KPI trends are available to leadership accounts"
        body="They roll the whole company's rolling-year history forward with a seasonal projection. Ask an owner or executive to share what you need."
        busy={loading}
        onRun={() => void load()}
      />
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
        {error ?? "Could not load the KPI trends."}
        <button className="ml-3 underline underline-offset-2" onClick={() => void load()}>
          Retry
        </button>
      </div>
    );
  }

  if (data.departments.length === 0) {
    return (
      <div className="panel px-6 py-16 text-center text-sm text-zinc-500">
        No trends to show yet. Connect ServiceTitan and QuickBooks and a rolling year of history builds
        automatically.
      </div>
    );
  }

  const dept = data.departments.find((d) => d.key === activeDept) ?? data.departments[0];
  // The catalog is the single source of truth the selector reads (every KPI per department).
  const catalog = data.catalog.filter((c) => c.department === dept.key);

  return (
    <div className="space-y-4">
      <div className="panel flex flex-wrap items-center justify-between gap-x-4 gap-y-3 px-5 py-3.5">
        <div className="flex flex-wrap items-center gap-1.5">
          {data.departments.map((d) => {
            const active = d.key === dept.key;
            const accent = DEPT_ACCENT[d.key] ?? FALLBACK_COLOR;
            return (
              <button
                key={d.key}
                type="button"
                onClick={() => setActiveDept(d.key)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                  active ? "text-zinc-100" : "text-zinc-400 hover:bg-white/[0.04] hover:text-zinc-200"
                }`}
                style={active ? { backgroundColor: `${accent}22`, color: accent } : undefined}
              >
                {d.label}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-2">
          <GranularityToggle value={granularity} onChange={setGranularity} />
        </div>
      </div>

      <DepartmentTrends
        key={dept.key}
        dept={dept}
        catalog={catalog}
        granularity={granularity}
        historyWeeks={data.history_weeks}
        forecastWeeks={data.forecast_weeks}
      />
    </div>
  );
}

function GranularityToggle({
  value,
  onChange,
}: {
  value: Granularity;
  onChange: (g: Granularity) => void;
}) {
  return (
    <div className="inline-flex rounded-lg border border-white/10 bg-white/[0.03] p-0.5" role="group" aria-label="Time grain">
      {(["weekly", "monthly"] as const).map((g) => (
        <button
          key={g}
          type="button"
          aria-pressed={value === g}
          onClick={() => onChange(g)}
          className={`rounded-md px-3 py-1 text-xs font-medium capitalize transition ${
            value === g ? "bg-accent/15 text-accent" : "text-zinc-400 hover:text-zinc-200"
          }`}
        >
          {g}
        </button>
      ))}
    </div>
  );
}

/** One department's trend grid: the KpiSelector (namespaced so it doesn't collide with the
 * scorecard's saved sets) + a responsive grid of forecast-aware KPI trend cards. */
function DepartmentTrends({
  dept,
  catalog,
  granularity,
  historyWeeks,
  forecastWeeks,
}: {
  dept: TrendDepartment;
  catalog: KpiDef[];
  granularity: Granularity;
  historyWeeks: number;
  forecastWeeks: number;
}) {
  const accent = DEPT_ACCENT[dept.key] ?? FALLBACK_COLOR;
  const validKeys = catalog.map((d) => d.key);
  // Defaults = the sensible exec set, intersected with what this department actually returns.
  const returnedKeys = new Set(dept.kpis.map((k) => k.key));
  const defaults = (DEFAULT_VISIBLE[dept.key] ?? [])
    .filter((k) => validKeys.includes(k) && returnedKeys.has(k));
  // Fall back to the department's first few returned KPIs when no default set matched.
  const effectiveDefaults =
    defaults.length > 0 ? defaults : dept.kpis.slice(0, 4).map((k) => k.key).filter((k) => validKeys.includes(k));
  // A "trends:" namespace so this reuses useVisibleKpis WITHOUT sharing the scorecard's saved keys.
  const { visible, toggle, reset, isDefault } = useVisibleKpis(
    `trends:${dept.key}`,
    validKeys,
    effectiveDefaults,
  );

  const kpiByKey = useMemo(
    () => new Map<string, TrendKpi>(dept.kpis.map((k) => [k.key, k])),
    [dept],
  );
  const cards = visible.map((key) => kpiByKey.get(key)).filter((k): k is TrendKpi => k !== undefined);

  return (
    <section className="panel overflow-hidden">
      <div className="border-l-2 px-5 py-3.5" style={{ borderLeftColor: accent }}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: accent }} />
            <h3 className="text-base font-semibold text-zinc-100">{dept.label}</h3>
            <span className="text-xs text-zinc-500">
              {historyWeeks}-week history · {forecastWeeks}-week projection
            </span>
          </div>
          <KpiSelector
            catalog={catalog}
            visible={visible}
            onToggle={toggle}
            onReset={reset}
            isDefault={isDefault}
          />
        </div>
      </div>

      <div className="p-4">
        {cards.length === 0 ? (
          <p className="px-1 py-8 text-center text-sm text-zinc-500">
            {catalog.length === 0
              ? "Metrics coming soon. This department isn't wired to a source yet."
              : "No KPIs selected. Use the KPIs menu to add some back."}
          </p>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {cards.map((kpi) => (
              <TrendCard key={kpi.key} kpi={kpi} accent={accent} granularity={granularity} />
            ))}
          </div>
        )}
      </div>

      <LegendRow accent={accent} />
    </section>
  );
}

/** A tiny legend distinguishing the solid ACTUAL line from the dashed PROJECTED band. */
function LegendRow({ accent }: { accent: string }) {
  return (
    <div className="flex flex-wrap items-center gap-4 border-t border-white/[0.06] px-5 py-2.5 text-[11px] text-zinc-500">
      <span className="inline-flex items-center gap-1.5">
        <span className="inline-block h-0.5 w-6 rounded-full" style={{ backgroundColor: accent }} />
        Actual (rolling year)
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span
          className="inline-block h-0 w-6 border-t-2 border-dashed"
          style={{ borderColor: accent }}
        />
        Projected (seasonal forecast)
      </span>
      <span className="text-zinc-600">Deterministic projection, no LLM guesses (ADR-0003).</span>
    </div>
  );
}

/** One KPI card: the big current value + goal + delta, over a full forecast-aware trend chart. */
function TrendCard({
  kpi,
  accent,
  granularity,
}: {
  kpi: TrendKpi;
  accent: string;
  granularity: Granularity;
}) {
  const points = granularity === "monthly" ? kpi.monthly : kpi.weekly;
  const hasData = points.some((p) => p.value !== null);

  // Color the delta by whether the movement is an IMPROVEMENT (respects lower-is-better KPIs), and
  // treat a flat (~0%) change as neutral — matching the scorecard's ScorecardKpiCard convention.
  const delta = kpi.delta_pct;
  const deltaFlat = delta !== null && Math.abs(delta) < 0.5;
  const deltaGood = delta !== null && !deltaFlat && (delta > 0) === kpi.higher_is_better;

  return (
    <div className="kpi !p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="label leading-snug">{kpi.label}</div>
          <div className="num mt-1.5 text-2xl font-semibold tracking-tight text-zinc-100">
            {fmtScorecardValue(kpi.current, kpi.unit)}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          {kpi.calculated && (
            <span
              className="shrink-0 rounded border border-accent/30 bg-accent/10 px-1 py-px text-[9px] font-semibold uppercase tracking-wide text-accent-soft"
              title="Calculated: derived from raw KPIs (ADR-0003)"
            >
              calc
            </span>
          )}
          {kpi.goal !== null && (
            <span
              className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-px text-[10px] font-medium ${
                kpi.on_goal === true
                  ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
                  : kpi.on_goal === false
                    ? "border-amber-400/30 bg-amber-400/10 text-amber-300"
                    : "border-white/10 bg-white/[0.04] text-zinc-400"
              }`}
              title={kpi.on_goal === false ? "Below goal" : kpi.on_goal === true ? "On goal" : "Goal"}
            >
              {kpi.on_goal === true ? "✓" : kpi.on_goal === false ? "▼" : ""} goal{" "}
              {fmtScorecardValue(kpi.goal, kpi.unit)}
            </span>
          )}
          {delta !== null && (
            <span
              className={`inline-flex items-center gap-0.5 text-[11px] ${
                deltaFlat ? "text-zinc-500" : deltaGood ? "text-emerald-400" : "text-amber-400"
              }`}
              title="Change vs the start of the rolling year (green = improvement)"
            >
              {deltaFlat ? "▬" : delta > 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(0)}%
            </span>
          )}
        </div>
      </div>

      <div className="mt-3">
        {hasData ? (
          <KpiTrendsChart
            points={points}
            unit={kpi.unit}
            color={accent}
            goal={kpi.goal}
            forecastFrom={kpi.forecast_from}
            granularity={granularity}
          />
        ) : (
          <div className="grid h-[260px] place-items-center text-[11px] text-zinc-600">
            Trend builds as history accumulates
          </div>
        )}
      </div>

      {kpi.description && (
        <div className="mt-2 truncate text-xs text-zinc-500" title={kpi.description}>
          {kpi.description}
        </div>
      )}
    </div>
  );
}
