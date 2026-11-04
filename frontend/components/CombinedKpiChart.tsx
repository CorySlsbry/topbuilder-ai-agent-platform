"use client";

import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
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
import type { KpiSeries, OrgKpiUnit } from "@/lib/types";

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

// Dollar metrics share the left axis; everything else (minutes, counts, hours) shares the right —
// so we can honestly overlay revenue vs. drive-time vs. headcount on ONE chart without faking a
// single scale across incompatible units.
const isDollar = (unit: OrgKpiUnit) => unit === "usd";

/** Many metric series on one chart, color-coded by department — the side-by-side comparison view.
 * Left Y = dollars, right Y = the other units, so mixed-unit series read truthfully together. */
export default function CombinedKpiChart({
  series,
  dates,
  height = 320,
}: {
  series: KpiSeries[];
  dates: string[];
  height?: number;
}) {
  const ref = useEChart(() => {
    const t = chartTheme();
    const hasDollar = series.some((s) => isDollar(s.unit));
    const hasOther = series.some((s) => !isDollar(s.unit));
    // Pick the dominant non-dollar unit for the right axis label (usually one such metric on screen).
    const otherUnit = series.find((s) => !isDollar(s.unit))?.unit ?? "count";
    return {
      color: series.map((s) => s.color ?? FALLBACK_COLOR),
      grid: { left: 58, right: hasOther ? 56 : 18, top: 36, bottom: 30 },
      legend: {
        type: "scroll",
        top: 2,
        icon: "roundRect",
        itemWidth: 12,
        itemHeight: 4,
        textStyle: { color: t.label, fontSize: 11 },
        data: series.map((s) => s.label),
      },
      tooltip: {
        trigger: "axis",
        order: "valueDesc",
        valueFormatter: (v: number | string) => (v === null || v === undefined ? "—" : `${v}`),
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: dates.map(shortDate),
        axisLine: { lineStyle: { color: t.axis } },
        axisLabel: { color: t.label, fontSize: 11 },
        axisTick: { show: false },
      },
      yAxis: [
        {
          type: "value",
          name: hasDollar ? "$" : "",
          nameTextStyle: { color: t.label },
          axisLabel: { formatter: unitAxisFormatter("usd"), color: t.label, fontSize: 11 },
          splitLine: { lineStyle: { color: t.split } },
        },
        {
          type: "value",
          position: "right",
          axisLabel: {
            formatter: unitAxisFormatter(otherUnit),
            color: t.label,
            fontSize: 11,
          },
          splitLine: { show: false },
        },
      ],
      series: series.map((s) => ({
        name: s.label,
        type: "line" as const,
        smooth: true,
        connectNulls: true,
        symbol: "circle",
        symbolSize: 6,
        yAxisIndex: isDollar(s.unit) ? 0 : 1,
        data: s.points.map((p) => p.value),
        lineStyle: { width: 2.5 },
        emphasis: { focus: "series" },
        // Per-series tooltip value uses that series' own unit formatter.
        tooltip: { valueFormatter: unitValueFormatter(s.unit) },
      })),
    };
  }, [series, dates]);
  return <div ref={ref} style={{ width: "100%", height }} />;
}
