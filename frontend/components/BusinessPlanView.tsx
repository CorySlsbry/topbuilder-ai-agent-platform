"use client";

import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { Fragment, useCallback, useEffect, useState } from "react";

import { chartTheme, useEChart } from "@/components/chartKit";
import { EmptyState, Panel, Spinner, usd } from "@/components/ui";
import { ApiError, apiRequest } from "@/lib/api";
import type { AnnualGoal, BudgetLine, BusinessPlan, TrailingPoint } from "@/lib/eos-types";

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

/** The Business Plan — the other sticky Bloom "communication hub" surface: the V/TO annual goals,
 * this period's budget-to-actual P&L, and a trailing-12 revenue + net-income trend (sourced from
 * QuickBooks P&L when live, per docs/QBO_DATA_MAP). Leadership-only (a 403 → leadership EmptyState).
 * Every figure is the deterministic engine's (ADR-0003); net income is derived, never keyed.
 * Theme-aware throughout (charts re-read the .light class via chartKit). */

const getBusinessPlan = (t: string) =>
  apiRequest<BusinessPlan>(t, "/v1/org/business-plan", "load the business plan");

const fmtGoal = (g: AnnualGoal, value: number | null): string => {
  if (value === null) return "—";
  switch (g.unit) {
    case "usd":
      return usd(value);
    case "percent":
      return `${Number(value.toFixed(1))}%`;
    case "ratio":
      return Number(value.toFixed(2)).toString();
    default:
      return value.toLocaleString("en-US");
  }
};

/** A signed dollar delta with a +/- sign (e.g. "+$2,250" / "-$18,300"). */
const signedUsd = (n: number): string => `${n >= 0 ? "+" : "-"}${usd(Math.abs(n))}`;

function GoalCard({ goal }: { goal: AnnualGoal }) {
  const tone =
    goal.on_track === null ? "text-zinc-100" : goal.on_track ? "text-emerald-300" : "text-amber-300";
  // Attainment caps the bar at 100% for the visual; "lower is better" goals invert the read so the
  // bar still fills as you approach the target ceiling (less is better).
  const raw = goal.attainment_pct;
  const pct =
    raw === null
      ? null
      : goal.higher_is_better
        ? Math.max(0, Math.min(raw, 100))
        : Math.max(0, Math.min(200 - raw, 100));
  const barColor = goal.on_track === false ? "#fbbf24" : "#34d399";
  return (
    <div className="kpi">
      <div className="flex items-start justify-between gap-2">
        <div className="label">{goal.label}</div>
        {goal.on_track !== null && (
          <span
            className={`inline-flex shrink-0 rounded-md border px-1.5 py-px text-[10px] font-medium ${
              goal.on_track
                ? "border-emerald-300/25 bg-emerald-300/10 text-emerald-300"
                : "border-amber-300/25 bg-amber-300/10 text-amber-300"
            }`}
          >
            {goal.on_track ? "On track" : "Off track"}
          </span>
        )}
      </div>
      <div className={`num mt-2 text-2xl font-semibold tracking-tight ${tone}`}>
        {fmtGoal(goal, goal.actual)}
      </div>
      <div className="mt-1 text-xs text-zinc-500">
        Goal {fmtGoal(goal, goal.target)}
        {raw !== null && <span className="text-zinc-600"> · {Number(raw.toFixed(0))}% of target</span>}
      </div>
      {pct !== null && (
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
          <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: barColor }} />
        </div>
      )}
    </div>
  );
}

const KIND_LABEL: Record<string, string> = { revenue: "Revenue", cogs: "Cost of goods", expense: "Expense" };

function BudgetRow({ line }: { line: BudgetLine }) {
  const tone = line.favorable ? "text-emerald-300" : "text-red-300";
  return (
    <tr className="border-t border-white/[0.05]">
      <td className="px-4 py-2.5 text-sm text-zinc-200">{line.label}</td>
      <td className="px-4 py-2.5 text-right num text-sm text-zinc-400">{usd(line.budget)}</td>
      <td className="px-4 py-2.5 text-right num text-sm text-zinc-100">{usd(line.actual)}</td>
      <td className={`px-4 py-2.5 text-right num text-sm ${tone}`}>{signedUsd(line.variance)}</td>
      <td className={`px-4 py-2.5 text-right num text-xs ${tone}`}>
        {line.variance_pct === null ? "—" : `${line.variance_pct >= 0 ? "+" : ""}${line.variance_pct}%`}
      </td>
    </tr>
  );
}

function TrailingChart({ points }: { points: TrailingPoint[] }) {
  const ref = useEChart(() => {
    const t = chartTheme();
    return {
      grid: { left: 56, right: 56, top: 28, bottom: 28 },
      legend: {
        top: 0,
        textStyle: { color: t.label, fontSize: 11 },
        data: ["Revenue", "Net income"],
      },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: number | string) => usd(Number(v)),
      },
      xAxis: {
        type: "category",
        data: points.map((p) => p.month),
        axisLine: { lineStyle: { color: t.axis } },
        axisLabel: { color: t.label, fontSize: 10 },
      },
      yAxis: [
        {
          type: "value",
          axisLabel: { formatter: (v: number) => `$${(v / 1000).toFixed(0)}k`, color: t.label },
          splitLine: { lineStyle: { color: t.split } },
        },
        {
          type: "value",
          axisLabel: { formatter: (v: number) => `$${(v / 1000).toFixed(0)}k`, color: t.label },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: "Revenue",
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 5,
          data: points.map((p) => p.revenue),
          itemStyle: { color: "#5b8cff" },
          areaStyle: { color: "rgba(91,140,255,0.12)" },
        },
        {
          name: "Net income",
          type: "line",
          yAxisIndex: 1,
          smooth: true,
          symbol: "circle",
          symbolSize: 5,
          data: points.map((p) => p.net_income),
          itemStyle: { color: "#34d399" },
        },
      ],
    };
  }, [points]);
  return <div ref={ref} style={{ width: "100%", height: 300 }} />;
}

export default function BusinessPlanView({ token }: { token: string }) {
  const [data, setData] = useState<BusinessPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setForbidden(false);
    try {
      setData(await getBusinessPlan(token));
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) setForbidden(true);
      else setError(e instanceof Error ? e.message : "Couldn't load the business plan.");
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
        <span className="mt-3 text-sm">Loading the business plan…</span>
      </div>
    );
  }

  if (forbidden) {
    return (
      <EmptyState
        title="The business plan is available to leadership accounts"
        body="Annual goals, budget-to-actual, and the trailing-12 P&L roll up the whole company — ask an owner or executive to share what you need."
        busy={loading}
        onRun={() => void load()}
      />
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
        {error ?? "Could not load the business plan."}
        <button className="ml-3 underline underline-offset-2" onClick={() => void load()}>Retry</button>
      </div>
    );
  }

  const { annual_goals: goals, budget_to_actual: bta, trailing_12: t12 } = data;
  const net = bta.totals.net_income;
  const hasTrailing = t12.points.length > 0;

  return (
    <div className="space-y-4">
      {/* ---- header ---- */}
      <div className="panel flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-5 py-3.5">
        <h2 className="text-sm font-semibold text-zinc-100">
          {data.company} — Business Plan · FY{data.fiscal_year}
        </h2>
        <span className="text-xs text-zinc-500">
          Annual goals · budget-to-actual ({data.period_label}) · trailing-12 — auto-pulled, not keyed
        </span>
      </div>

      {/* ---- annual goals ---- */}
      <Panel title="Annual goals" aside={`${goals.length}`}>
        {goals.length === 0 ? (
          <div className="px-5 py-10 text-center text-sm text-zinc-500">No annual goals set yet.</div>
        ) : (
          <div className="grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-3">
            {goals.map((g) => (
              <GoalCard key={g.key} goal={g} />
            ))}
          </div>
        )}
      </Panel>

      {/* ---- budget to actual ---- */}
      <Panel title={`Budget to actual — ${data.period_label}`} aside={KIND_LABEL.revenue}>
        {bta.lines.length === 0 ? (
          <div className="px-5 py-10 text-center text-sm text-zinc-500">
            Connect QuickBooks and the budget-to-actual fills in from the P&amp;L automatically.
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="text-left">
                    <th className="px-4 py-2 label">Line</th>
                    <th className="px-4 py-2 label text-right">Budget</th>
                    <th className="px-4 py-2 label text-right">Actual</th>
                    <th className="px-4 py-2 label text-right">Variance</th>
                    <th className="px-4 py-2 label text-right">%</th>
                  </tr>
                </thead>
                <tbody>
                  {(["revenue", "cogs", "expense"] as const).map((kind) => {
                    const rows = bta.lines.filter((l) => l.kind === kind);
                    if (rows.length === 0) return null;
                    const block = bta.totals[kind];
                    return (
                      <Fragment key={kind}>
                        {rows.map((l) => (
                          <BudgetRow key={l.key} line={l} />
                        ))}
                        <tr className="border-t border-white/10 bg-white/[0.02]">
                          <td className="px-4 py-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">
                            Total {KIND_LABEL[kind]}
                          </td>
                          <td className="px-4 py-2 text-right num text-xs text-zinc-400">{usd(block.budget)}</td>
                          <td className="px-4 py-2 text-right num text-xs text-zinc-200">{usd(block.actual)}</td>
                          <td className="px-4 py-2 text-right num text-xs text-zinc-400">{signedUsd(block.variance)}</td>
                          <td className="px-4 py-2" />
                        </tr>
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {/* derived net income */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 px-4 py-3.5">
              <div>
                <div className="label">Net income (derived: revenue − COGS − expense)</div>
                <div className="mt-1 flex items-baseline gap-3">
                  <span className={`num text-2xl font-semibold tracking-tight ${net.favorable ? "text-emerald-300" : "text-red-300"}`}>
                    {usd(net.actual)}
                  </span>
                  <span className="text-xs text-zinc-500">vs {usd(net.budget)} planned</span>
                </div>
              </div>
              <span
                className={`rounded-md border px-2.5 py-1 text-sm font-medium ${
                  net.favorable
                    ? "border-emerald-300/25 bg-emerald-300/10 text-emerald-300"
                    : "border-red-300/25 bg-red-300/10 text-red-300"
                }`}
              >
                {signedUsd(net.variance)} {net.favorable ? "ahead of plan" : "behind plan"}
              </span>
            </div>
          </>
        )}
      </Panel>

      {/* ---- trailing 12 ---- */}
      <Panel
        title="Trailing 12 months"
        aside={hasTrailing ? `${t12.totals.months} mo · ${usd(t12.totals.revenue)} rev` : undefined}
      >
        {!hasTrailing ? (
          <div className="px-5 py-10 text-center text-sm text-zinc-500">
            Trailing-12 history builds as months close — connect QuickBooks to populate it.
          </div>
        ) : (
          <div className="p-4">
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="kpi">
                <div className="label">TTM revenue</div>
                <div className="num mt-2 text-2xl font-semibold tracking-tight text-zinc-100">{usd(t12.totals.revenue)}</div>
              </div>
              <div className="kpi">
                <div className="label">TTM net income</div>
                <div className="num mt-2 text-2xl font-semibold tracking-tight text-emerald-300">{usd(t12.totals.net_income)}</div>
              </div>
              <div className="kpi">
                <div className="label">Blended net margin</div>
                <div className="num mt-2 text-2xl font-semibold tracking-tight text-zinc-100">
                  {t12.totals.net_margin_pct === null ? "—" : `${t12.totals.net_margin_pct}%`}
                </div>
              </div>
            </div>
            <div className="mt-4">
              <TrailingChart points={t12.points} />
            </div>
            <p className="mt-3 px-1 text-xs leading-relaxed text-zinc-500">
              Revenue (left axis) and net income (right axis) by month — the backwards view Bloom Growth
              can&apos;t give you. Sourced from the QuickBooks P&amp;L when connected.
            </p>
          </div>
        )}
      </Panel>
    </div>
  );
}
