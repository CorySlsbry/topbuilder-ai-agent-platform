"use client";

import { BarChart } from "echarts/charts";
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useMemo, useState } from "react";

import { chartTheme, useEChart } from "@/components/chartKit";
import { Badge, Confidence, Kpi, Panel } from "@/components/ui";
// Single source of truth — the capacity contract mirrors backend capacity_schemas.CapacityRunResult.
import type { CapacityRunResult, TechDuration, TechWeekProjection } from "@/lib/types";

echarts.use([BarChart, GridComponent, LegendComponent, TooltipComponent, MarkLineComponent, CanvasRenderer]);

const h = (n: number | null | undefined): string =>
  n === null || n === undefined || Number.isNaN(n) ? "—" : `${Number(n.toFixed(1))}h`;

// A projection is "heading into OT" when overtime_hours > 0; "slack" when projected is comfortably
// under contracted (>= ~3h headroom). Everything else is "on track". These are presentational reads
// of the engine's already-computed figures (ADR-0003 — never recomputed here).
const SLACK_HOURS = 3;
type Pace = "faster" | "slower" | "on baseline";
type Load = "overtime" | "slack" | "ontrack";

const loadOf = (p: TechWeekProjection): Load => {
  if (p.overtime_hours > 0) return "overtime";
  if (p.contracted_hours - p.projected_hours >= SLACK_HOURS) return "slack";
  return "ontrack";
};

const PACE_TONE: Record<Pace, string> = {
  faster: "text-emerald-300",
  slower: "text-amber-300",
  "on baseline": "text-zinc-400",
};
const PACE_LABEL: Record<Pace, string> = {
  faster: "faster than baseline",
  slower: "slower than baseline",
  "on baseline": "on baseline",
};

/** Projected vs contracted hours per tech, overtime stacked in red — the OT bars chart. */
function OvertimeChart({ projections }: { projections: TechWeekProjection[] }) {
  const ref = useEChart(() => {
    const t = chartTheme();
    // Within-contract hours render blue; the overtime slice stacks on top in red so OT reads instantly.
    const names = projections.map((p) => p.technician_id);
    const withinContract = projections.map((p) => Math.max(0, p.projected_hours - p.overtime_hours));
    const overtime = projections.map((p) => p.overtime_hours);
    const contracted = projections.length ? projections[0].contracted_hours : 0;
    return {
      grid: { left: 90, right: 20, top: 28, bottom: 28 },
      legend: { top: 0, right: 8, textStyle: { color: t.label, fontSize: 11 }, icon: "roundRect", itemWidth: 11, itemHeight: 11 },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v: number | string) => `${Number(v).toFixed(1)}h` },
      xAxis: {
        type: "value",
        axisLabel: { formatter: (v: number) => `${v}h`, color: t.label },
        splitLine: { lineStyle: { color: t.split } },
      },
      yAxis: {
        type: "category",
        inverse: true,
        data: names,
        axisLine: { lineStyle: { color: t.axis } },
        axisLabel: { color: t.label, fontSize: 11 },
      },
      series: [
        {
          name: "Within contract",
          type: "bar",
          stack: "load",
          barMaxWidth: 16,
          data: withinContract,
          itemStyle: { color: "#5b8cff", borderRadius: [4, 0, 0, 4] },
          // The contracted-hours line: a marker so "who crosses the line" is obvious.
          markLine: contracted
            ? {
                symbol: "none",
                silent: true,
                lineStyle: { color: "#f2b65a", type: "dashed", width: 1.5 },
                label: { formatter: `contracted ${Number(contracted.toFixed(0))}h`, color: t.label, fontSize: 10, position: "insideEndTop" },
                data: [{ xAxis: contracted }],
              }
            : undefined,
        },
        {
          name: "Overtime",
          type: "bar",
          stack: "load",
          barMaxWidth: 16,
          data: overtime,
          itemStyle: { color: "#f87171", borderRadius: [0, 4, 4, 0] },
        },
      ],
    };
  }, [projections]);
  return <div ref={ref} style={{ width: "100%", height: Math.max(180, projections.length * 34 + 60) }} />;
}

export default function CapacityView({ data }: { data: CapacityRunResult }) {
  const t = data.totals;
  const [trade, setTrade] = useState<string>("all");

  const trades = useMemo(
    () => Array.from(new Set(data.durations.map((d) => d.trade))).sort(),
    [data.durations],
  );
  const durations = useMemo(
    () => (trade === "all" ? data.durations : data.durations.filter((d) => d.trade === trade)),
    [data.durations, trade],
  );

  // Projections ordered so the people heading into OT surface first, then least slack.
  const projections = useMemo(
    () => [...data.projections].sort((a, b) => b.overtime_hours - a.overtime_hours
      || (b.projected_hours - b.contracted_hours) - (a.projected_hours - a.contracted_hours)),
    [data.projections],
  );
  const overtimeTechs = projections.filter((p) => p.overtime_hours > 0);
  const slackTechs = projections.filter((p) => loadOf(p) === "slack");

  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Technicians" value={String(t.technicians)} tone="neutral" />
        <Kpi label="Learned estimates" value={String(t.duration_pairs)} tone="info" />
        <Kpi
          label="Heading into overtime"
          value={String(t.techs_over_capacity)}
          tone={t.techs_over_capacity ? "warn" : "ok"}
        />
        <Kpi
          label="Projected OT next week"
          value={h(t.total_overtime_hours)}
          tone={t.total_overtime_hours > 0 ? "bad" : "ok"}
        />
      </section>

      {/* ---- the week projection: OT bars + the narrative ---- */}
      <section className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="panel p-5 lg:col-span-3">
          <div className="mb-1 flex items-baseline justify-between">
            <h2 className="text-sm font-semibold text-zinc-100">Next week: projected hours vs contracted</h2>
            <span className="label">overtime in red</span>
          </div>
          {projections.length === 0 ? (
            <p className="px-1 py-10 text-center text-sm text-zinc-500">
              No week projection yet — run the analysis to forecast hours from each tech&apos;s learned pace.
            </p>
          ) : (
            <OvertimeChart projections={projections} />
          )}
        </div>
        <div className="panel p-5 lg:col-span-2">
          <h2 className="mb-2 text-sm font-semibold text-zinc-100">Capacity narrative</h2>
          <p className="label mb-3">deterministic figures · LLM/template narration</p>
          <div className="max-h-[300px] overflow-auto whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-300">
            {data.reasoning_logs || "No narrative for this run."}
          </div>
        </div>
      </section>

      {/* ---- who's heading into OT and who has slack ---- */}
      <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Panel title="Heading into overtime" aside={`${overtimeTechs.length} tech${overtimeTechs.length === 1 ? "" : "s"}`}>
          {overtimeTechs.length === 0 ? (
            <p className="px-5 py-6 text-sm text-zinc-500">No technician is projected into overtime next week.</p>
          ) : (
            <div className="divide-y divide-white/[0.05]">
              {overtimeTechs.map((p) => (
                <div key={p.technician_id} className="px-5 py-3.5">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-zinc-100">{p.technician_id}</span>
                      <Badge label={p.trade} />
                    </div>
                    <div className="num text-right text-sm">
                      <span className="font-semibold text-red-300">{h(p.projected_hours)}</span>
                      <span className="text-zinc-600"> / {h(p.contracted_hours)}</span>
                    </div>
                  </div>
                  <div className="mt-1.5 flex items-center justify-between gap-3">
                    <span className="text-xs text-amber-300">
                      {h(p.overtime_hours)} over · {p.job_count} job{p.job_count === 1 ? "" : "s"}
                    </span>
                    <Confidence value={p.confidence} />
                  </div>
                  {p.redistribute_to.length > 0 && (
                    <p className="mt-2 text-xs leading-relaxed text-zinc-400">
                      Redistribute to{" "}
                      <span className="font-medium text-emerald-300">{p.redistribute_to.join(", ")}</span>
                    </p>
                  )}
                  {p.reasoning && <p className="mt-1 text-xs leading-relaxed text-zinc-500">{p.reasoning}</p>}
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Has slack" aside={`${slackTechs.length} tech${slackTechs.length === 1 ? "" : "s"}`}>
          {slackTechs.length === 0 ? (
            <p className="px-5 py-6 text-sm text-zinc-500">
              No clear slack — everyone is close to their contracted hours.
            </p>
          ) : (
            <div className="divide-y divide-white/[0.05]">
              {slackTechs.map((p) => {
                const free = p.contracted_hours - p.projected_hours;
                return (
                  <div key={p.technician_id} className="flex items-center justify-between gap-3 px-5 py-3.5">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-zinc-100">{p.technician_id}</span>
                      <Badge label={p.trade} />
                    </div>
                    <div className="text-right">
                      <div className="num text-sm font-semibold text-emerald-300">{h(free)} free</div>
                      <div className="num text-[11px] text-zinc-600">
                        {h(p.projected_hours)} / {h(p.contracted_hours)}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Panel>
      </section>

      {/* ---- per-tech rolling durations: faster/slower than baseline + confidence ---- */}
      <Panel
        title="Rolling job durations vs baseline"
        aside={
          trades.length > 1 ? (
            <select
              value={trade}
              onChange={(e) => setTrade(e.target.value)}
              className="rounded-md border border-white/10 bg-white/[0.04] px-2 py-1 text-xs text-zinc-300 focus:outline-none"
              aria-label="Filter by trade"
            >
              <option value="all">All trades</option>
              {trades.map((tr) => (
                <option key={tr} value={tr}>
                  {tr}
                </option>
              ))}
            </select>
          ) : (
            `${durations.length} estimates`
          )
        }
      >
        {durations.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">No learned durations yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                  <th>Technician</th>
                  <th>Job type</th>
                  <th className="text-right">Estimate</th>
                  <th className="text-right">Baseline</th>
                  <th>Pace</th>
                  <th className="text-right">Samples</th>
                  <th>Confidence</th>
                </tr>
              </thead>
              <tbody>
                {durations.map((d) => (
                  <DurationRow key={`${d.technician_id}-${d.job_type}`} d={d} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}

function DurationRow({ d }: { d: TechDuration }) {
  const pace = d.pace as Pace;
  const delta = d.efficiency_delta_hours;
  return (
    <tr className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
      <td className="font-medium text-zinc-100">
        {d.technician_id} <Badge label={d.trade} />
      </td>
      <td className="text-zinc-300">{d.job_type}</td>
      <td className="num text-right font-medium text-zinc-100">{h(d.estimate_hours)}</td>
      <td className="num text-right text-zinc-500">{h(d.baseline_hours)}</td>
      <td>
        <span className={`text-xs font-medium ${PACE_TONE[pace] ?? "text-zinc-400"}`}>
          {pace === "on baseline" ? PACE_LABEL[pace] : `${h(Math.abs(delta))} ${PACE_LABEL[pace] ?? "on baseline"}`}
        </span>
      </td>
      <td className="num text-right text-zinc-400">{d.sample_size}</td>
      <td>
        <Confidence value={d.confidence} />
      </td>
    </tr>
  );
}
