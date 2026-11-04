"use client";

import * as echarts from "echarts/core";
import { type DependencyList, useEffect, useRef } from "react";

import type { OrgKpiUnit } from "@/lib/types";

/** Neutral chart palette that re-reads on the `.light` class toggle (the app flips it on <html>). */
export const chartTheme = () =>
  typeof document !== "undefined" && document.documentElement.classList.contains("light")
    ? { label: "#52525b", axis: "#d4d4d8", split: "rgba(0,0,0,0.06)", track: "rgba(0,0,0,0.04)" }
    : { label: "#9aa3b2", axis: "#2b3242", split: "rgba(255,255,255,0.05)", track: "rgba(255,255,255,0.04)" };

/** init/dispose + window resize + re-render when the `.light` class toggles on <html>.
 * Identical contract to ExecutiveView.useEChart so charts stay theme-consistent across the app. */
export function useEChart(build: () => echarts.EChartsCoreOption, deps: DependencyList) {
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

export const FALLBACK_COLOR = "#5b8cff";

/** Compact axis/tooltip formatter for a KPI unit. usd -> $k on the axis, full $ in tooltips. */
export function unitAxisFormatter(unit: OrgKpiUnit): (v: number) => string {
  switch (unit) {
    case "usd":
      return (v) => `$${Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(0)}k` : v.toFixed(0)}`;
    case "minutes_per_day":
      return (v) => `${Math.round(v)}m`;
    case "hours":
      return (v) => `${Number(v.toFixed(1))}h`;
    default:
      return (v) => v.toLocaleString("en-US");
  }
}

export function unitValueFormatter(unit: OrgKpiUnit): (v: number | string) => string {
  switch (unit) {
    case "usd":
      return (v) => `$${Number(v).toLocaleString("en-US")}`;
    case "minutes_per_day":
      return (v) => `${Math.round(Number(v))} min/day`;
    case "hours":
      return (v) => `${Number(Number(v).toFixed(1))}h`;
    default:
      return (v) => Number(v).toLocaleString("en-US");
  }
}

/** "Jun 3" style short date for a YYYY-MM-DD axis label. */
export const shortDate = (iso: string): string => {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
};
