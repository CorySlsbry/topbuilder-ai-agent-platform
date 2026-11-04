"use client";

import { useState } from "react";

import { chartTheme, FALLBACK_COLOR, useEChart } from "@/components/chartKit";
import { fmtScorecardValue } from "@/components/DepartmentSection";
import type { DepartmentScorecard, EntityRow, KpiDef, ScorecardUnit } from "@/lib/types";

const ROLE_LABEL: Record<string, { singular: string; plural: string }> = {
  sales_rep: { singular: "rep", plural: "Sales reps" },
  technician: { singular: "technician", plural: "Technicians" },
  csr: { singular: "call taker", plural: "Call takers (CSRs)" },
};

/** Sort entities high→low on the active metric so the leader is on top; nulls sink to the bottom. */
function rankEntities(entities: EntityRow[], key: string, higherIsBetter: boolean): EntityRow[] {
  return [...entities].sort((a, b) => {
    const av = a.values[key];
    const bv = b.values[key];
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    return higherIsBetter ? bv - av : av - bv;
  });
}

/** Horizontal-bar comparison of every entity on the active metric — Cory's explicit "close rates
 * side by side". Theme-aware (re-reads on the `.light` toggle). */
function ComparisonBars({
  entities,
  metricKey,
  unit,
  accent,
}: {
  entities: EntityRow[];
  metricKey: string;
  unit: ScorecardUnit;
  accent: string;
}) {
  // Inverse category axis renders the first row at the top — feed it leader-first.
  const rows = entities.filter((e) => e.values[metricKey] !== null && e.values[metricKey] !== undefined);
  const height = Math.max(120, rows.length * 34 + 24);

  const ref = useEChart(() => {
    const t = chartTheme();
    const fmtAxis = (v: number) => {
      switch (unit) {
        case "usd":
          return `$${Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(0)}k` : v.toFixed(0)}`;
        case "percent":
          return `${v}%`;
        case "hours":
          return `${v}h`;
        default:
          return v.toLocaleString("en-US");
      }
    };
    return {
      grid: { left: 4, right: 56, top: 8, bottom: 24, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        valueFormatter: (v: number | string) => fmtScorecardValue(Number(v), unit),
      },
      xAxis: {
        type: "value",
        axisLabel: { formatter: fmtAxis, color: t.label, fontSize: 11 },
        splitLine: { lineStyle: { color: t.split } },
      },
      yAxis: {
        type: "category",
        inverse: true,
        data: rows.map((e) => e.entity_name),
        axisLine: { lineStyle: { color: t.axis } },
        axisTick: { show: false },
        axisLabel: { color: t.label, fontSize: 11 },
      },
      series: [
        {
          type: "bar",
          barMaxWidth: 18,
          data: rows.map((e, i) => ({
            value: e.values[metricKey],
            // Leader (top row) gets the full accent; the rest fade slightly for a clean ranking read.
            itemStyle: { color: i === 0 ? accent : `${accent}b3`, borderRadius: [0, 4, 4, 0] },
          })),
          label: {
            show: true,
            position: "right",
            color: t.label,
            fontSize: 11,
            formatter: (p: { value: number }) => fmtScorecardValue(p.value, unit),
          },
        },
      ],
    };
  }, [rows, metricKey, unit, accent]);

  return <div ref={ref} style={{ width: "100%", height }} />;
}

/** The per-entity side-by-side panel: a metric switcher among entity_kpi_keys, a horizontal-bar
 * comparison on the active metric, and a compact table of every entity's values across all
 * entity_kpi_keys. Used for Sales (reps), Operations (techs), Sales+Marketing (CSRs). */
export default function RepPanel({
  department,
  catalog,
  accent,
}: {
  department: DepartmentScorecard;
  catalog: KpiDef[];
  accent: string;
}) {
  const roleKey = department.entity_role ?? "";
  const role = ROLE_LABEL[roleKey] ?? { singular: "person", plural: "People" };
  const defByKey = new Map<string, KpiDef>(catalog.map((d) => [d.key, d]));
  const metricKeys = department.entity_kpi_keys.filter((k) => defByKey.has(k));
  // Boolean flags (e.g. needs_coaching) render as flags in the table — never charted or ranked as a number.
  const chartKeys = metricKeys.filter((k) => defByKey.get(k)?.unit !== "bool");
  const [active, setActive] = useState<string>(chartKeys[0] ?? "");

  const empty = department.entities.length === 0 || metricKeys.length === 0;

  if (empty) {
    return (
      <div className="mt-4 rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-6 text-center">
        <div className="text-sm font-medium text-zinc-300">{role.plural} — side by side</div>
        <p className="mt-1 text-xs text-zinc-500">
          Metric coming soon — per-{role.singular} breakdowns appear here once this department&apos;s source
          is connected.
        </p>
      </div>
    );
  }

  const activeDef = defByKey.get(active);
  const activeUnit = activeDef?.unit ?? "count";
  const higherIsBetter = activeDef?.higher_is_better ?? true;
  const ranked = rankEntities(department.entities, active, higherIsBetter);
  const hasAnyActiveValue = ranked.some((e) => e.values[active] !== null && e.values[active] !== undefined);

  return (
    <div className="mt-4 rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm font-semibold text-zinc-100">
          {role.plural} <span className="text-zinc-500">side by side</span>
        </div>
        <div className="flex flex-wrap gap-1">
          {chartKeys.map((key) => {
            const on = key === active;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setActive(key)}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                  on
                    ? "text-white"
                    : "border border-white/10 bg-white/[0.02] text-zinc-400 hover:bg-white/[0.06] hover:text-zinc-200"
                }`}
                style={on ? { backgroundColor: accent } : undefined}
              >
                {defByKey.get(key)?.label ?? key}
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-3">
        {hasAnyActiveValue ? (
          <ComparisonBars entities={ranked} metricKey={active} unit={activeUnit} accent={accent} />
        ) : (
          <p className="px-1 py-6 text-center text-xs text-zinc-500">
            No values for {activeDef?.label ?? active} yet — pick another metric or check back after the next sync.
          </p>
        )}
      </div>

      {/* Compact table — every entity's value across all entity_kpi_keys (the full board). */}
      <div className="mt-3 overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-white/[0.06] text-left">
              <th className="label py-1.5 pr-3 font-medium">{role.plural.replace(/s$/, "")}</th>
              {metricKeys.map((key) => (
                <th
                  key={key}
                  className={`label py-1.5 pl-3 text-right font-medium ${key === active ? "text-accent-soft" : ""}`}
                >
                  {defByKey.get(key)?.label ?? key}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ranked.map((e) => (
              <tr key={e.entity_id} className="border-b border-white/[0.04] last:border-0">
                <td className="num py-1.5 pr-3 text-zinc-200">{e.entity_name}</td>
                {metricKeys.map((key) => (
                  <td
                    key={key}
                    className={`num py-1.5 pl-3 text-right ${
                      key === active ? "font-semibold text-zinc-100" : "text-zinc-400"
                    }`}
                  >
                    {fmtScorecardValue(e.values[key] ?? null, defByKey.get(key)?.unit ?? "count")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
