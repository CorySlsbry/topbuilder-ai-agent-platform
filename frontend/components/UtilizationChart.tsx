"use client";

import * as echarts from "echarts";
import { useEffect, useRef } from "react";

import type { TradeUtilization } from "@/lib/types";

const PALETTE: Record<string, string> = {
  hvac: "#5b8cff",
  plumbing: "#22c3a6",
  electrical: "#f2b65a",
  install: "#9b8cff",
};

export default function UtilizationChart({ data }: { data: TradeUtilization[] }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, undefined, { renderer: "canvas" });

    const trades = Array.from(new Set(data.map((d) => d.trade)));
    const weeks = Array.from(new Set(data.map((d) => d.week_offset))).sort((a, b) => a - b);

    const series: echarts.SeriesOption[] = trades.map((trade) => ({
      name: trade,
      type: "bar",
      barMaxWidth: 26,
      itemStyle: { color: PALETTE[trade] ?? "#7c8aa5", borderRadius: [4, 4, 0, 0] },
      data: weeks.map((w) => {
        const row = data.find((d) => d.trade === trade && d.week_offset === w);
        return row ? Math.round(row.utilization * 100) : 0;
      }),
    }));

    // dashed "Capacity 100%" reference line carried on an empty line series
    series.push({
      type: "line",
      data: [],
      markLine: {
        silent: true,
        symbol: "none",
        lineStyle: { color: "#f2606a", type: "dashed" },
        data: [{ yAxis: 100 }],
        label: { formatter: "Capacity 100%", color: "#f2606a", position: "insideEndTop" },
      },
    });

    chart.setOption({
      grid: { left: 46, right: 16, top: 30, bottom: 34 },
      legend: { top: 0, textStyle: { color: "#9aa3b2" }, icon: "roundRect" },
      tooltip: { trigger: "axis", valueFormatter: (v: number | string) => `${v}%` },
      xAxis: {
        type: "category",
        data: weeks.map((w) => (w === 0 ? "This week" : `Week +${w}`)),
        axisLine: { lineStyle: { color: "#2b3242" } },
        axisLabel: { color: "#9aa3b2" },
      },
      yAxis: {
        type: "value",
        axisLabel: { formatter: "{value}%", color: "#9aa3b2" },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.05)" } },
      },
      series,
    });

    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [data]);

  return <div ref={ref} style={{ width: "100%", height: 300 }} />;
}
