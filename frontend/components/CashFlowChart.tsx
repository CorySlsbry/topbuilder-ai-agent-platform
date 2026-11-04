"use client";

import * as echarts from "echarts";
import { useEffect, useRef } from "react";

import type { CashFlowBucket } from "@/lib/types";

export default function CashFlowChart({ data }: { data: CashFlowBucket[] }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, undefined, { renderer: "canvas" });
    const labels = data.map((b) => `${b.horizon_days}d`);

    chart.setOption({
      grid: { left: 64, right: 56, top: 30, bottom: 34 },
      legend: { top: 0, textStyle: { color: "#9aa3b2" }, icon: "roundRect" },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: number | string) => `$${Number(v).toLocaleString()}`,
      },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { lineStyle: { color: "#2b3242" } },
        axisLabel: { color: "#9aa3b2" },
      },
      yAxis: [
        {
          type: "value",
          name: "flow",
          axisLabel: { formatter: (v: number) => `$${(v / 1000).toFixed(0)}k`, color: "#9aa3b2" },
          splitLine: { lineStyle: { color: "rgba(255,255,255,0.05)" } },
        },
        {
          type: "value",
          name: "cash",
          position: "right",
          axisLabel: { formatter: (v: number) => `$${(v / 1000).toFixed(0)}k`, color: "#9aa3b2" },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: "Inflows",
          type: "bar",
          stack: "flow",
          data: data.map((b) => b.inflows),
          itemStyle: { color: "#46d3b6", borderRadius: [4, 4, 0, 0] },
          barMaxWidth: 22,
        },
        {
          name: "Outflows",
          type: "bar",
          stack: "flow",
          data: data.map((b) => -b.outflows),
          itemStyle: { color: "#f2606a", borderRadius: [0, 0, 4, 4] },
          barMaxWidth: 22,
        },
        {
          name: "Projected cash",
          type: "line",
          yAxisIndex: 1,
          smooth: true,
          symbolSize: 8,
          data: data.map((b) => b.projected_cash),
          lineStyle: { color: "#5b8cff", width: 3 },
          itemStyle: { color: "#5b8cff" },
          areaStyle: { color: "rgba(91,140,255,0.12)" },
        },
      ],
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
