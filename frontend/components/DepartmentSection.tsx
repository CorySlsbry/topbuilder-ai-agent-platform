"use client";

import KpiSelector, { useVisibleKpis } from "@/components/KpiSelector";
import { Sparkline } from "@/components/KpiTrendChart";
import RepPanel from "@/components/RepPanel";
import { usd } from "@/components/ui";
import { FALLBACK_COLOR } from "@/components/chartKit";
import type {
  DepartmentScorecard,
  KpiDef,
  KpiSeries,
  KpiValue,
  ScorecardUnit,
  SeriesPoint,
} from "@/lib/types";

// Per-department accent — drives the section header rule + the sparkline tint so the four
// departments read as visually distinct bands. Keyed to the scorecard dept keys.
const DEPT_ACCENT: Record<string, string> = {
  sales: "#fb7185",
  operations: "#34d399",
  sales_marketing: "#38bdf8",
  finance: "#818cf8",
};

const SOURCE_BADGE: Record<string, string> = {
  ServiceTitan: "#5b8cff",
  QuickBooks: "#2ca01c",
};

/** Format a scorecard value for its unit. Returns the em-dash for null (never NaN/empty). */
export function fmtScorecardValue(value: number | null, unit: ScorecardUnit): string {
  if (value === null || Number.isNaN(value)) return "—";
  switch (unit) {
    case "usd":
      return usd(value);
    case "percent":
      return `${Number(value.toFixed(1))}%`;
    case "ratio":
      return Number(value.toFixed(2)).toLocaleString("en-US");
    case "hours":
      return `${Number(value.toFixed(1))}h`;
    case "minutes_per_day":
      return `${Math.round(value)}m/day`;
    case "bool":
      return value ? "Yes" : "No";
    default:
      return value.toLocaleString("en-US");
  }
}

/** Format the goal chip text ("goal $145k" etc.) — compact so it fits the chip. */
function fmtGoal(goal: number, unit: ScorecardUnit): string {
  switch (unit) {
    case "usd":
      return Math.abs(goal) >= 1000 ? `$${(goal / 1000).toFixed(goal % 1000 === 0 ? 0 : 1)}k` : usd(goal);
    case "percent":
      return `${Number(goal.toFixed(1))}%`;
    case "ratio":
      return Number(goal.toFixed(2)).toLocaleString("en-US");
    case "hours":
      return `${Number(goal.toFixed(1))}h`;
    case "minutes_per_day":
      return `${Math.round(goal)}m/day`;
    default:
      return goal.toLocaleString("en-US");
  }
}

const chip = (color: string) => ({ color, backgroundColor: `${color}1f`, borderColor: `${color}40` });

/** Adapt the scorecard KpiValue's series to the KpiSeries shape the shared Sparkline reads.
 * (Sparkline only consumes `points` + `color`; `unit`/`agent` are along for the type.) */
function toSparkSeries(kpi: KpiValue, def: KpiDef | undefined, color: string): KpiSeries {
  const points: SeriesPoint[] = kpi.series ?? [];
  return {
    key: kpi.key,
    label: def?.label ?? kpi.key,
    agent: "",
    department: null,
    color,
    // Sparkline ignores unit; the safe units overlap, so report the closest OrgKpiUnit.
    unit: def?.unit === "minutes_per_day" || def?.unit === "hours" ? def.unit : "count",
    points,
  };
}

function ScorecardKpiCard({
  kpi,
  def,
  accent,
}: {
  kpi: KpiValue;
  def: KpiDef | undefined;
  accent: string;
}) {
  const unit = def?.unit ?? "count";
  const hasTrend = (kpi.series?.filter((p) => p.value !== null).length ?? 0) >= 2;
  const onGoal = kpi.on_goal; // true | false | null
  // Color the period delta by whether the movement is an IMPROVEMENT (respects lower-is-better KPIs
  // like debt / idle / AR-over-30), and treat a flat (~0%) change as neutral — not "up / green".
  const hib = def?.higher_is_better ?? true;
  const delta = kpi.delta_pct;
  const deltaFlat = delta !== null && Math.abs(delta) < 0.5;
  const deltaGood = delta !== null && !deltaFlat && (delta > 0) === hib;

  return (
    <div className="kpi !p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="label leading-snug">{def?.label ?? kpi.key}</div>
        {def?.calculated && (
          <span
            className="shrink-0 rounded border border-accent/30 bg-accent/10 px-1 py-px text-[9px] font-semibold uppercase tracking-wide text-accent-soft"
            title="Calculated — derived from raw KPIs (ADR-0003)"
          >
            calc
          </span>
        )}
      </div>

      <div className="num mt-2 text-2xl font-semibold tracking-tight text-zinc-100">
        {fmtScorecardValue(kpi.value, unit)}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {kpi.goal !== null && (
          <span
            className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-px text-[10px] font-medium ${
              onGoal === true
                ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
                : onGoal === false
                  ? "border-amber-400/30 bg-amber-400/10 text-amber-300"
                  : "border-white/10 bg-white/[0.04] text-zinc-400"
            }`}
            title={onGoal === false ? "Below goal" : onGoal === true ? "On goal" : "Goal"}
          >
            {onGoal === true ? "✓" : onGoal === false ? "▼" : ""} goal {fmtGoal(kpi.goal, unit)}
          </span>
        )}
        {delta !== null && (
          <span
            className={`inline-flex items-center gap-0.5 text-[11px] ${
              deltaFlat ? "text-zinc-500" : deltaGood ? "text-emerald-400" : "text-amber-400"
            }`}
            title="Change vs the first week in the period (green = improvement)"
          >
            {deltaFlat ? "▬" : delta > 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(0)}%
          </span>
        )}
      </div>

      <div className="mt-2.5 h-9">
        {hasTrend ? (
          <Sparkline series={toSparkSeries(kpi, def, accent)} height={36} />
        ) : (
          <div className="flex h-full items-center text-[11px] text-zinc-600">
            Trend builds over the next few weeks
          </div>
        )}
      </div>

      {def?.description && (
        <div className="mt-2 truncate text-xs text-zinc-500" title={def.description}>
          {def.description}
        </div>
      )}
    </div>
  );
}

/** One department band: header (label + source badge + KpiSelector) → a responsive grid of the
 * SELECTED KpiCards → the per-entity RepPanel when the department has an entity_role. Visually
 * separated from the next band by its own panel + accent rule. */
export default function DepartmentSection({
  department,
  catalog,
}: {
  department: DepartmentScorecard;
  catalog: KpiDef[];
}) {
  const accent = DEPT_ACCENT[department.key] ?? FALLBACK_COLOR;
  const badgeColor = SOURCE_BADGE[department.source] ?? FALLBACK_COLOR;

  // Defaults = the keys the backend actually returns for this department (its primary set).
  // The selector lists EVERY catalog KPI for the dept so the rest can be added.
  const validKeys = catalog.map((d) => d.key);
  const defaultKeys = department.kpis.map((k) => k.key).filter((k) => validKeys.includes(k));
  const { visible, toggle, reset, isDefault } = useVisibleKpis(department.key, validKeys, defaultKeys);

  const defByKey = new Map<string, KpiDef>(catalog.map((d) => [d.key, d]));
  const kpiByKey = new Map<string, KpiValue>(department.kpis.map((k) => [k.key, k]));
  // Render in catalog order, only the visible keys that have a computed value object.
  const cards = visible.map((key) => kpiByKey.get(key)).filter((k): k is KpiValue => k !== undefined);

  return (
    <section className="panel overflow-hidden">
      <div
        className="border-l-2 px-5 py-3.5"
        style={{ borderLeftColor: accent }}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: accent }} />
            <h3 className="text-base font-semibold text-zinc-100">{department.label}</h3>
            <span
              className="inline-flex items-center rounded-md border px-1.5 py-px text-[10px] font-medium uppercase tracking-wide"
              style={chip(badgeColor)}
            >
              {department.source}
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
              ? "Metrics coming soon — this department isn't wired to a source yet."
              : "No KPIs selected — use the KPIs menu to add some back."}
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {cards.map((kpi) => (
              <ScorecardKpiCard key={kpi.key} kpi={kpi} def={defByKey.get(kpi.key)} accent={accent} />
            ))}
          </div>
        )}

        {department.entity_role && (
          <RepPanel
            department={department}
            catalog={catalog}
            accent={accent}
          />
        )}
      </div>
    </section>
  );
}
