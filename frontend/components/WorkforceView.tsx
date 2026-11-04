"use client";

import UtilizationChart from "@/components/UtilizationChart";
import { Badge, Confidence, Kpi, Panel, usd } from "@/components/ui";
import type { WorkforceRunResult } from "@/lib/types";

export default function WorkforceView({ data }: { data: WorkforceRunResult }) {
  const t = data.totals;
  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Trade-weeks short" value={String(t.weeks_short)} tone={t.weeks_short ? "warn" : "ok"} />
        <Kpi label="At-risk margin" value={usd(t.total_understaffing_impact_usd)} tone="warn" />
        <Kpi label="Techs in overtime" value={String(t.technicians_in_overtime)} tone={t.technicians_in_overtime ? "warn" : "ok"} />
        <Kpi label="Avoidable OT premium" value={usd(t.total_overtime_premium_usd)} tone="info" />
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="panel p-5 lg:col-span-3">
          <div className="mb-1 flex items-baseline justify-between">
            <h2 className="text-sm font-semibold text-zinc-100">Projected demand vs. capacity</h2>
            <span className="label">by trade · next {data.horizon_days}d</span>
          </div>
          <UtilizationChart data={data.utilization} />
        </div>
        <div className="panel p-5 lg:col-span-2">
          <h2 className="mb-2 text-sm font-semibold text-zinc-100">Advisor narrative</h2>
          <p className="label mb-3">deterministic figures · LLM/template narration</p>
          <div className="max-h-[300px] overflow-auto whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-300">
            {data.reasoning_logs}
          </div>
        </div>
      </section>

      <Panel title="Understaffing risks" aside={`${data.understaffing_risks.length} flagged`}>
        {data.understaffing_risks.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">No understaffing detected in the horizon.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                <th>Week of</th><th>Trade</th><th className="text-right">Gap</th>
                <th className="text-right">Add techs</th><th className="text-right">At-risk margin</th><th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {data.understaffing_risks.map((r) => (
                <tr key={`${r.trade_type}-${r.week_offset}`} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                  <td className="num text-zinc-300">{r.week_start}</td>
                  <td><Badge label={r.trade_type} /></td>
                  <td className="num text-right text-zinc-300">{r.gap_hours.toFixed(1)}h</td>
                  <td className="num text-right text-amber-300">{r.gap_count}</td>
                  <td className="num text-right font-medium text-zinc-100">{usd(r.economic_impact_usd)}</td>
                  <td><Confidence value={r.confidence} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel title="Overtime risks" aside={`${data.overtime_risks.length} flagged`}>
        {data.overtime_risks.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">No avoidable overtime detected.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                <th>Technician</th><th>Trade</th><th className="text-right">OT hours</th>
                <th className="text-right">Premium</th><th>Mitigation</th><th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {data.overtime_risks.map((r) => (
                <tr key={r.technician_id} className="border-b border-white/[0.04] last:border-0 align-top [&>td]:px-5 [&>td]:py-3">
                  <td className="font-medium text-zinc-100">{r.technician_name}</td>
                  <td><Badge label={r.trade} /></td>
                  <td className="num text-right text-amber-300">{r.projected_overtime_hours.toFixed(1)}h</td>
                  <td className="num text-right font-medium text-zinc-100">{usd(r.economic_impact_usd)}</td>
                  <td className="max-w-[320px] text-xs leading-relaxed text-zinc-400">{r.mitigation_strategy}</td>
                  <td><Confidence value={r.confidence} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
