"use client";

import { LineChart } from "echarts/charts";
import {
  GridComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

import {
  chartTheme,
  FALLBACK_COLOR,
  shortDate,
  unitAxisFormatter,
  unitValueFormatter,
  useEChart,
} from "@/components/chartKit";
import type { KpiSeries, ScorecardUnit, TrendPoint } from "@/lib/types";

echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  MarkLineComponent,
  MarkAreaComponent,
  CanvasRenderer,
]);

const presentValues = (s: KpiSeries): number[] =>
  s.points.map((p) => p.value).filter((v): v is number => v !== null);

const fmtCompact = (v: number, unit: KpiSeries["unit"]): string => unitAxisFormatter(unit)(v);

/** A full historical line+area chart for ONE metric — the "go backwards" view Bloom can't give.
 * Connects across gap days (null points) so a sparse run history still reads as a trend. */
export default function KpiTrendChart({ series, height = 220 }: { series: KpiSeries; height?: number }) {
  const color = series.color ?? FALLBACK_COLOR;
  const ref = useEChart(() => {
    const t = chartTheme();
    const vals = presentValues(series);
    const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    return {
      grid: { left: 52, right: 16, top: 16, bottom: 26 },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: number | string) =>
          v === null || v === undefined ? "—" : unitValueFormatter(series.unit)(v),
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: series.points.map((p) => shortDate(p.date)),
        axisLine: { lineStyle: { color: t.axis } },
        axisLabel: { color: t.label, fontSize: 11 },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        axisLabel: { formatter: (v: number) => fmtCompact(v, series.unit), color: t.label, fontSize: 11 },
        splitLine: { lineStyle: { color: t.split } },
      },
      series: [
        {
          name: series.label,
          type: "line",
          smooth: true,
          connectNulls: true,
          symbol: "circle",
          symbolSize: 6,
          showSymbol: vals.length <= 12,
          data: series.points.map((p) => p.value),
          lineStyle: { color, width: 2.5 },
          itemStyle: { color },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: `${color}33` },
              { offset: 1, color: `${color}05` },
            ]),
          },
          ...(avg !== null && vals.length > 1
            ? {
                markLine: {
                  silent: true,
                  symbol: "none",
                  lineStyle: { color, type: "dashed", opacity: 0.5 },
                  label: {
                    formatter: `avg ${fmtCompact(avg, series.unit)}`,
                    color: t.label,
                    fontSize: 10,
                  },
                  data: [{ yAxis: avg }],
                },
              }
            : {}),
        },
      ],
    };
  }, [series]);
  return <div ref={ref} style={{ width: "100%", height }} />;
}

// ====================================================================================================
// Premium KPI Trends chart — the forecast-aware variant for the KPI Trends view.
// Renders the rolling-year ACTUALS as a solid gradient area, then the deterministic forward BAND
// (projected points) as a DASHED line over a shaded region, split by a vertical "forecast start"
// divider. The two segments share the boundary point so the line reads as one continuous curve.
// ====================================================================================================

/** Compact dollars for an axis ($1.2M / $18k / $940). */
function usdCompact(v: number): string {
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1_000_000) return `${sign}$${Number((a / 1_000_000).toFixed(1))}M`;
  if (a >= 1_000) return `${sign}$${Number((a / 1_000).toFixed(a >= 100_000 ? 0 : 1))}k`;
  return `${sign}$${Math.round(a)}`;
}

/** Axis-tick label formatter per scorecard unit (compact — fits a narrow left gutter). */
export function trendAxisFormatter(unit: ScorecardUnit): (v: number) => string {
  switch (unit) {
    case "usd":
      return usdCompact;
    case "percent":
      return (v) => `${Number(v.toFixed(v % 1 === 0 ? 0 : 1))}%`;
    case "ratio":
      return (v) => `${Number(v.toFixed(1))}x`;
    case "hours":
      return (v) => `${Number(v.toFixed(1))}h`;
    case "minutes_per_day":
      return (v) => `${Math.round(v)}m`;
    case "bool":
      return (v) => (v >= 0.5 ? "Yes" : "No");
    default:
      return (v) => v.toLocaleString("en-US");
  }
}

/** Full-precision value formatter per scorecard unit (tooltips + the big current value). */
export function trendValueFormatter(unit: ScorecardUnit): (v: number) => string {
  switch (unit) {
    case "usd":
      return (v) => `$${Math.round(v).toLocaleString("en-US")}`;
    case "percent":
      return (v) => `${Number(v.toFixed(1))}%`;
    case "ratio":
      return (v) => `${Number(v.toFixed(2))}x`;
    case "hours":
      return (v) => `${Number(v.toFixed(1))}h`;
    case "minutes_per_day":
      return (v) => `${Math.round(v)} min/day`;
    case "bool":
      return (v) => (v ? "Yes" : "No");
    default:
      return (v) => v.toLocaleString("en-US");
  }
}

/** A month-name axis: "Jul", showing the year on January so a rolling year reads left→right. */
function monthAxisLabel(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.getMonth() === 0
    ? d.toLocaleDateString("en-US", { month: "short", year: "2-digit" })
    : d.toLocaleDateString("en-US", { month: "short" });
}

/** Split a projected-tagged series into an actual line and a forecast line that overlap at the
 * boundary point, so ECharts draws one continuous curve (solid → dashed) with no gap. Each output
 * array is the FULL length (nulls elsewhere) so both share the single category axis. */
function splitActualForecast(points: TrendPoint[]): { actual: (number | null)[]; forecast: (number | null)[] } {
  const firstProjected = points.findIndex((p) => p.projected);
  // The solid actual line ends at the last real actual (never draws into the projected region).
  const actual = points.map((p) => (p.projected ? null : p.value));
  const forecast = points.map((p, i) => {
    if (p.projected) return p.value;
    // Seed the dashed forecast line at the single last actual point (i = firstProjected-1) so the
    // two segments visually connect at the boundary without the solid line entering the band.
    if (firstProjected > 0 && i === firstProjected - 1) return p.value;
    return null;
  });
  return { actual, forecast };
}

/** The premium single-KPI trend chart: rolling-year actuals (solid gradient area) + a distinct
 * dashed forecast band over a shaded forward region, a vertical divider at the forecast start, and
 * an optional goal reference line. Handles null gaps (connectNulls) and mixed weekly/monthly points. */
export function KpiTrendsChart({
  points,
  unit,
  color = FALLBACK_COLOR,
  goal = null,
  forecastFrom = null,
  granularity = "weekly",
  height = 260,
}: {
  points: TrendPoint[];
  unit: ScorecardUnit;
  color?: string;
  goal?: number | null;
  forecastFrom?: string | null;
  granularity?: "weekly" | "monthly";
  height?: number;
}) {
  const ref = useEChart(() => {
    const t = chartTheme();
    const { actual, forecast } = splitActualForecast(points);
    const dates = points.map((p) => p.date);
    const hasForecast = forecast.some((v) => v !== null);
    // The divider + shaded region sit on the first projected category.
    const dividerDate = forecastFrom ?? points.find((p) => p.projected)?.date ?? null;
    const dividerLabel = dividerDate ? (granularity === "monthly" ? monthAxisLabel(dividerDate) : shortDate(dividerDate)) : null;
    const lastDate = dates.length ? dates[dates.length - 1] : null;
    const axisLabel = granularity === "monthly" ? monthAxisLabel : shortDate;
    const fmtVal = trendValueFormatter(unit);

    return {
      grid: { left: 56, right: 18, top: 18, bottom: 26 },
      tooltip: {
        trigger: "axis" as const,
        // Tag projected points; the two series overlap at the boundary so de-dup by showing one row.
        formatter: (params: unknown) => {
          const arr = (Array.isArray(params) ? params : [params]) as {
            axisValueLabel?: string;
            axisValue?: string;
            dataIndex: number;
            value: number | null;
          }[];
          const idx = arr[0]?.dataIndex ?? 0;
          const p = points[idx];
          if (!p) return "";
          const label = arr[0]?.axisValueLabel ?? arr[0]?.axisValue ?? p.date;
          const v = p.value === null ? "no data" : fmtVal(p.value);
          const tag = p.projected
            ? ' <span style="opacity:.7">(projected)</span>'
            : "";
          return `${label}<br/><strong>${v}</strong>${tag}`;
        },
      },
      xAxis: {
        type: "category" as const,
        boundaryGap: false,
        data: dates.map(axisLabel),
        axisLine: { lineStyle: { color: t.axis } },
        axisLabel: {
          color: t.label,
          fontSize: 11,
          // Thin the ticks so a 52+26 week series doesn't overprint month names.
          interval: (i: number) => {
            if (granularity === "monthly") return true;
            const step = Math.max(1, Math.ceil(dates.length / 12));
            return i % step === 0;
          },
        },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value" as const,
        scale: true,
        axisLabel: { formatter: trendAxisFormatter(unit), color: t.label, fontSize: 11 },
        splitLine: { lineStyle: { color: t.split } },
      },
      series: [
        {
          name: "Actual",
          type: "line" as const,
          smooth: true,
          connectNulls: true,
          symbol: "none",
          data: actual,
          lineStyle: { color, width: 2.5 },
          itemStyle: { color },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: `${color}38` },
              { offset: 1, color: `${color}05` },
            ]),
          },
          z: 3,
          // The goal reference line + the forecast divider ride on this series.
          markLine:
            goal !== null || dividerLabel !== null
              ? {
                  silent: true,
                  symbol: "none" as const,
                  data: [
                    ...(goal !== null
                      ? [
                          {
                            yAxis: goal,
                            lineStyle: { color: t.label, type: "dashed" as const, opacity: 0.55, width: 1 },
                            label: {
                              formatter: `goal ${fmtVal(goal)}`,
                              color: t.label,
                              fontSize: 10,
                              position: "insideEndTop" as const,
                            },
                          },
                        ]
                      : []),
                    ...(dividerLabel !== null
                      ? [
                          {
                            xAxis: dividerLabel,
                            lineStyle: { color, type: "dotted" as const, opacity: 0.55, width: 1.5 },
                            label: {
                              formatter: "forecast",
                              color,
                              fontSize: 10,
                              position: "insideEndTop" as const,
                            },
                          },
                        ]
                      : []),
                  ],
                }
              : undefined,
          // Shade the forward region so "projection ahead" reads at a glance.
          markArea:
            hasForecast && dividerLabel !== null && lastDate !== null
              ? {
                  silent: true,
                  itemStyle: { color: `${color}0f` },
                  data: [
                    [
                      { xAxis: dividerLabel },
                      { xAxis: granularity === "monthly" ? monthAxisLabel(lastDate) : shortDate(lastDate) },
                    ],
                  ],
                }
              : undefined,
        },
        {
          name: "Projected",
          type: "line" as const,
          smooth: true,
          connectNulls: true,
          symbol: "none",
          data: forecast,
          lineStyle: { color, width: 2, type: "dashed" as const, opacity: 0.9 },
          itemStyle: { color },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: `${color}18` },
              { offset: 1, color: `${color}02` },
            ]),
          },
          z: 2,
        },
      ],
    };
  }, [points, unit, color, goal, forecastFrom, granularity]);
  return <div ref={ref} style={{ width: "100%", height }} />;
}

/** Tiny inline trend used inside KPI cards — area only, no axes. */
export function Sparkline({ series, height = 40 }: { series: KpiSeries; height?: number }) {
  const color = series.color ?? FALLBACK_COLOR;
  const ref = useEChart(() => {
    return {
      grid: { left: 0, right: 0, top: 4, bottom: 0 },
      xAxis: { type: "category", show: false, boundaryGap: false, data: series.points.map((p) => p.date) },
      yAxis: { type: "value", show: false, scale: true },
      tooltip: { show: false },
      series: [
        {
          type: "line",
          smooth: true,
          connectNulls: true,
          symbol: "none",
          data: series.points.map((p) => p.value),
          lineStyle: { color, width: 2 },
          areaStyle: { color: `${color}22` },
        },
      ],
    };
  }, [series]);
  return <div ref={ref} style={{ width: "100%", height }} />;
}
