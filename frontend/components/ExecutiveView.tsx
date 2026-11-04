"use client";

import { BarChart, PieChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { type DependencyList, useCallback, useEffect, useRef, useState } from "react";

import CombinedKpiChart from "@/components/CombinedKpiChart";
import KpiTrendChart from "@/components/KpiTrendChart";
import ScorecardView from "@/components/ScorecardView";
import { EmptyState, Panel, Spinner, usd } from "@/components/ui";
import { ApiError, getOrgKpis, getOrgKpisTimeseries } from "@/lib/api";
import type { OrgKpi, OrgKpis, OrgKpiTimeseries } from "@/lib/types";

echarts.use([BarChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

// Mirrors the /v1/org/overview agent cards (first key = home department) — colors come from
// headcount_by_department, so only the agent→department mapping is duplicated here.
const AGENT_DEPTS: Record<string, string[]> = {
  workforce: ["field", "leadership"],
  financial: ["finance", "leadership"],
  inventory: ["warehouse"],
  booking: ["front_office", "sales"],
  routing: ["dispatch"],
  documents: ["front_office", "finance"],
};

// Fallback palette (mirrors the page-level DEPT_COLORS) for before/without the API colors.
const DEPT_COLORS: Record<string, string> = {
  leadership: "#f59e0b",
  front_office: "#38bdf8",
  dispatch: "#a78bfa",
  field: "#34d399",
  sales: "#fb7185",
  finance: "#818cf8",
  warehouse: "#fb923c",
};

const FALLBACK_COLOR = "#5b8cff";

const chip = (color: string) => ({ color, backgroundColor: `${color}1f`, borderColor: `${color}40` });

// Neutral chart colors that re-read on theme toggle (the app flips `.light` on <html>).
const chartTheme = () =>
  document.documentElement.classList.contains("light")
    ? { label: "#52525b", axis: "#d4d4d8", split: "rgba(0,0,0,0.06)" }
    : { label: "#9aa3b2", axis: "#2b3242", split: "rgba(255,255,255,0.05)" };

/** init/dispose + window resize + re-render when the `.light` class toggles on <html>. */
function useEChart(build: () => echarts.EChartsCoreOption, deps: DependencyList) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, undefined, { renderer: "canvas" });
    const render = () => chart.setOption(build(), true);
    render();
    const observer = new MutationObserver(render);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return ref;
}

const fmtKpi = (k: OrgKpi): string => {
  if (k.value === null) return "—";
  switch (k.unit) {
    case "usd":
      return usd(k.value);
    case "minutes_per_day":
      return `${Math.round(k.value)}m/day`;
    case "hours":
      return `${Number(k.value.toFixed(1))}h`;
    default:
      return k.value.toLocaleString("en-US");
  }
};

function KpiCard({ kpi, color, primary }: { kpi: OrgKpi; color: string | null; primary: boolean }) {
  return (
    <div
      className={`kpi ${primary ? "!border-accent/40" : ""}`}
      style={primary ? { boxShadow: "0 0 36px -14px rgba(91,140,255,0.55)" } : undefined}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="label">{kpi.label}</div>
        {kpi.agent && color && (
          <span className="inline-flex shrink-0 rounded-md border px-1.5 py-px text-[10px] font-medium capitalize" style={chip(color)}>
            {kpi.agent}
          </span>
        )}
      </div>
      <div className={`num mt-2 font-semibold tracking-tight ${primary ? "text-3xl text-accent-soft" : "text-2xl text-zinc-100"}`}>
        {fmtKpi(kpi)}
      </div>
      <div className="mt-1.5 text-xs leading-relaxed text-zinc-500">{kpi.detail}</div>
    </div>
  );
}

function ValueByAgentChart({ data, colorFor }: { data: OrgKpis["value_by_agent"]; colorFor: (agent: string) => string }) {
  const ref = useEChart(() => {
    const t = chartTheme();
    return {
      grid: { left: 110, right: 24, top: 10, bottom: 30 },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: number | string) => `$${Number(v).toLocaleString()}`,
      },
      xAxis: {
        type: "value",
        axisLabel: { formatter: (v: number) => `$${(v / 1000).toFixed(0)}k`, color: t.label },
        splitLine: { lineStyle: { color: t.split } },
      },
      yAxis: {
        type: "category",
        inverse: true,
        data: data.map((v) => v.label),
        axisLine: { lineStyle: { color: t.axis } },
        axisLabel: { color: t.label },
      },
      series: [
        {
          name: "Value identified",
          type: "bar",
          barMaxWidth: 18,
          data: data.map((v) => ({
            value: v.usd,
            itemStyle: { color: colorFor(v.agent), borderRadius: [0, 4, 4, 0] },
          })),
        },
      ],
    };
  }, [data]);
  return <div ref={ref} style={{ width: "100%", height: 280 }} />;
}

function HeadcountDonut({ data, employeeCount }: { data: OrgKpis["headcount_by_department"]; employeeCount: number }) {
  const ref = useEChart(() => {
    const t = chartTheme();
    return {
      tooltip: { trigger: "item", valueFormatter: (v: number | string) => `${v} people` },
      legend: {
        orient: "vertical",
        right: 8,
        top: "middle",
        icon: "circle",
        itemWidth: 9,
        itemHeight: 9,
        textStyle: { color: t.label, fontSize: 11 },
      },
      series: [
        {
          name: "Headcount",
          type: "pie",
          center: ["34%", "50%"],
          radius: ["58%", "82%"],
          avoidLabelOverlap: false,
          label: { show: false },
          labelLine: { show: false },
          data: data.map((d) => ({
            name: d.name,
            value: d.head_count,
            itemStyle: { color: d.color, borderRadius: 4 },
          })),
        },
      ],
    };
  }, [data]);
  return (
    <div className="relative">
      <div ref={ref} style={{ width: "100%", height: 280 }} />
      {/* HTML center label — keeps the figure readable in both themes without TitleComponent. */}
      <div
        className="pointer-events-none absolute text-center"
        style={{ left: "34%", top: "50%", transform: "translate(-50%, -50%)" }}
      >
        <div className="num text-2xl font-semibold tracking-tight text-zinc-100">{employeeCount}</div>
        <div className="label">employees</div>
      </div>
    </div>
  );
}

type ExecTab = "overview" | "combined" | "trends" | "departments";

const TABS: { key: ExecTab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "combined", label: "Combined" },
  { key: "trends", label: "Trends" },
  { key: "departments", label: "By Department" },
];

export default function ExecutiveView({ token }: { token: string }) {
  const [data, setData] = useState<OrgKpis | null>(null);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<ExecTab>("overview");
  const [history, setHistory] = useState<OrgKpiTimeseries | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setForbidden(false);
    try {
      setData(await getOrgKpis(token));
    } catch (e) {
      // A 403 means a department-scoped principal — show the leadership EmptyState, not an error.
      if (e instanceof ApiError && e.status === 403) setForbidden(true);
      else setError(e instanceof Error ? e.message : "Couldn't load the executive view.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      setHistory(await getOrgKpisTimeseries(token));
    } catch (e) {
      setHistoryError(e instanceof Error ? e.message : "Couldn't load the KPI history.");
    } finally {
      setHistoryLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  // Lazily fetch history the first time a history-backed tab is opened. The "departments" tab is
  // backed by the scorecard endpoint (ScorecardView fetches its own data), so it's excluded here.
  useEffect(() => {
    if (
      tab !== "overview" &&
      tab !== "departments" &&
      history === null &&
      !historyLoading &&
      historyError === null
    ) {
      void loadHistory();
    }
  }, [tab, history, historyLoading, historyError, loadHistory]);

  if (loading && !data) {
    return (
      <div className="panel grid place-items-center px-6 py-20 text-zinc-500">
        <Spinner />
        <span className="mt-3 text-sm">Loading executive KPIs…</span>
      </div>
    );
  }

  if (forbidden) {
    return (
      <EmptyState
        title="The Executive view is available to leadership accounts"
        body="Enterprise KPIs roll up every agent's results across departments — ask an owner or executive to share what you need."
        busy={loading}
        onRun={() => void load()}
      />
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
        {error ?? "Could not load the executive view"}
        <button className="ml-3 underline underline-offset-2" onClick={() => void load()}>Retry</button>
      </div>
    );
  }

  const deptColor: Record<string, string> = { ...DEPT_COLORS };
  for (const d of data.headcount_by_department) deptColor[d.key] = d.color;
  const colorFor = (agent: string | null): string => {
    const home = agent ? AGENT_DEPTS[agent]?.[0] : undefined;
    return (home ? deptColor[home] : undefined) ?? FALLBACK_COLOR;
  };

  // A department is covered when an agent with a persisted latest run serves it (same rule the
  // API uses for departments_covered — value null means "no run yet").
  const activeAgents = new Set(data.kpis.filter((k) => k.agent && k.value !== null).map((k) => k.agent as string));
  const covered = new Set(
    Object.entries(AGENT_DEPTS)
      .filter(([agent]) => activeAgents.has(agent))
      .flatMap(([, depts]) => depts),
  );

  return (
    <div className="space-y-4">
      {/* ---- tab bar ---- */}
      <div className="flex items-center gap-1 overflow-x-auto rounded-xl border border-white/[0.06] bg-white/[0.02] p-1">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-lg px-3.5 py-1.5 text-sm font-medium transition ${
              tab === t.key
                ? "bg-accent text-white shadow-sm"
                : "text-zinc-400 hover:bg-white/[0.06] hover:text-zinc-200"
            }`}
          >
            {t.label}
          </button>
        ))}
        <span className="ml-auto px-2 text-xs text-zinc-500">
          {tab === "overview"
            ? "Today's snapshot"
            : "History & trends — go backwards, not just red/green"}
        </span>
      </div>

      {tab === "overview" && (
        <OverviewTab data={data} colorFor={colorFor} covered={covered} />
      )}

      {/* The "By Department" tab is the auto-computed scorecard (the Bloom Growth L10 replacement),
          which fetches its own data from /v1/org/scorecard. */}
      {tab === "departments" && <ScorecardView token={token} />}

      {tab !== "overview" && tab !== "departments" && (
        <HistoryTabs
          tab={tab}
          history={history}
          loading={historyLoading}
          error={historyError}
          onRetry={() => void loadHistory()}
        />
      )}
    </div>
  );
}

function OverviewTab({
  data,
  colorFor,
  covered,
}: {
  data: OrgKpis;
  colorFor: (agent: string | null) => string;
  covered: Set<string>;
}) {
  return (
    <div className="space-y-4">
      {/* ---- KPI grid ---- */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {data.kpis.map((k) => (
          <KpiCard
            key={k.key}
            kpi={k}
            color={k.agent ? colorFor(k.agent) : null}
            primary={k.key === "total_value_identified"}
          />
        ))}
      </div>

      {/* ---- charts ---- */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Value identified by agent" aside={`${data.runs_present} runs`}>
          <div className="p-4">
            {data.value_by_agent.length === 0 ? (
              <p className="px-1 py-10 text-center text-sm text-zinc-500">No agent runs yet — run an agent to see value here.</p>
            ) : (
              <ValueByAgentChart data={data.value_by_agent} colorFor={colorFor} />
            )}
          </div>
        </Panel>
        <Panel title="Headcount by department" aside={`${data.headcount_by_department.length} departments`}>
          <div className="p-4">
            <HeadcountDonut data={data.headcount_by_department} employeeCount={data.employee_count} />
          </div>
        </Panel>
      </div>

      {/* ---- coverage strip ---- */}
      <div className="panel px-5 py-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <span className="text-sm font-semibold text-zinc-100">
            AI coverage: {data.departments_covered} of {data.headcount_by_department.length} departments
          </span>
          <span className="text-xs text-zinc-500">
            {data.agents_active} active agent{data.agents_active === 1 ? "" : "s"} · served by an active agent
          </span>
        </div>
        <div className="mt-3 flex gap-1.5">
          {data.headcount_by_department.map((d) => {
            const on = covered.has(d.key);
            return (
              <div key={d.key} className="min-w-0 flex-1" title={`${d.name} — ${on ? "covered" : "no active agent"}`}>
                <div
                  className="h-2 rounded-full"
                  style={{ backgroundColor: on ? d.color : `${d.color}2e`, opacity: on ? 1 : 0.6 }}
                />
                <div className={`mt-1.5 truncate text-center text-[10px] ${on ? "text-zinc-400" : "text-zinc-600"}`}>
                  {d.name}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function HistoryTabs({
  tab,
  history,
  loading,
  error,
  onRetry,
}: {
  // "departments" is handled by ScorecardView (its own endpoint), so only history tabs reach here.
  tab: Exclude<ExecTab, "overview" | "departments">;
  history: OrgKpiTimeseries | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  if (loading && !history) {
    return (
      <div className="panel grid place-items-center px-6 py-16 text-zinc-500">
        <Spinner />
        <span className="mt-3 text-sm">Loading KPI history…</span>
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
        {error}
        <button className="ml-3 underline underline-offset-2" onClick={onRetry}>Retry</button>
      </div>
    );
  }
  if (!history) return null;

  const hasData = history.dates.length > 0 && history.series.some((s) => s.points.some((p) => p.value !== null));
  if (!hasData) {
    return (
      <div className="panel px-6 py-16 text-center text-sm text-zinc-500">
        No history yet — run the agents a few times and their results build a trend here automatically.
        <div className="mt-2 text-xs text-zinc-600">This is what replaces hand-keying Bloom Growth every week.</div>
      </div>
    );
  }

  if (tab === "combined") {
    return (
      <Panel title="All agent KPIs, side by side" aside={`${history.dates.length} days`}>
        <div className="p-4">
          <CombinedKpiChart series={history.series} dates={history.dates} />
          <p className="mt-3 px-1 text-xs leading-relaxed text-zinc-500">
            Dollar metrics share the left axis; minutes and counts use the right — color-coded by
            department. Compare revenue recovery against drive-time and headcount on one timeline.
          </p>
        </div>
      </Panel>
    );
  }

  // tab === "trends"
  const withData = history.series.filter((s) => s.points.some((p) => p.value !== null));
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {withData.map((s) => (
        <Panel key={s.key} title={s.label} aside={s.agent}>
          <div className="p-4">
            <KpiTrendChart series={s} />
          </div>
        </Panel>
      ))}
    </div>
  );
}
