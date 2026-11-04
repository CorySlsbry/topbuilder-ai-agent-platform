"use client";

import CashFlowChart from "@/components/CashFlowChart";
import { Badge, Confidence, Kpi, Panel, usd } from "@/components/ui";
import type { FinancialRunResult } from "@/lib/types";

export default function FinancialView({ data }: { data: FinancialRunResult }) {
  const t = data.totals;
  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Projects at risk" value={String(t.projects_at_risk)} tone={t.projects_at_risk ? "warn" : "ok"} />
        <Kpi label="Margin leakage" value={usd(t.total_leakage_usd)} tone="bad" />
        <Kpi label="Cash @ 90 days" value={usd(t.cash_90_day)} tone="ok" />
        <Kpi label="Weakest segment" value={t.lowest_margin_segment ?? "—"} tone="info" />
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="panel p-5 lg:col-span-3">
          <div className="mb-1 flex items-baseline justify-between">
            <h2 className="text-sm font-semibold text-zinc-100">Cash-flow projection</h2>
            <span className="label">30 / 60 / 90 day · from {usd(data.starting_cash)}</span>
          </div>
          <CashFlowChart data={data.cash_flow_projection} />
        </div>
        <div className="panel p-5 lg:col-span-2">
          <h2 className="mb-2 text-sm font-semibold text-zinc-100">CFO narrative</h2>
          <p className="label mb-3">GAAP percentage-of-completion · LLM/template narration</p>
          <div className="max-h-[300px] overflow-auto whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-300">
            {data.reasoning_logs}
          </div>
        </div>
      </section>

      <Panel title="WIP profitability" aside={`${data.wip_profitability.length} active projects`}>
        <table className="w-full text-sm">
          <thead>
            <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
              <th>Project</th><th>Segment</th><th className="text-right">Index</th>
              <th className="text-right">Margin / budget</th><th className="text-right">Billing</th><th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {data.wip_profitability.map((j) => (
              <tr key={j.job_id} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                <td className="font-medium text-zinc-100">{j.name}</td>
                <td><Badge label={j.customer_segment} /></td>
                <td className={`num text-right font-medium ${j.profitability_index < 1 ? "text-amber-300" : "text-emerald-300"}`}>
                  {j.profitability_index.toFixed(2)}
                </td>
                <td className="num text-right text-zinc-300">
                  {(j.margin_to_date * 100).toFixed(1)}% <span className="text-zinc-600">/ {(j.budget_margin * 100).toFixed(0)}%</span>
                </td>
                <td className={`num text-right ${j.billing_position >= 0 ? "text-zinc-400" : "text-amber-300"}`}>
                  {j.billing_position >= 0 ? "+" : "−"}{usd(Math.abs(j.billing_position))}
                </td>
                <td><Confidence value={j.confidence} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Panel title="Margin leakage" aside={`${data.leakage_warnings.length} flagged`}>
            {data.leakage_warnings.length === 0 ? (
              <p className="px-5 py-6 text-sm text-zinc-500">All projects on target.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                    <th>Project</th><th>Type</th><th className="text-right">Exposure</th><th>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {data.leakage_warnings.map((w) => (
                    <tr key={w.job_id} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                      <td className="font-medium text-zinc-100">{w.name}</td>
                      <td className="text-xs uppercase tracking-wide text-zinc-400">{w.kind.replace("_", " ")}</td>
                      <td className="num text-right font-medium text-red-300">{usd(w.severity_usd)}</td>
                      <td><Confidence value={w.confidence} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        </div>
        <Panel title="Segment margins">
          <table className="w-full text-sm">
            <tbody>
              {data.segment_margins.map((s) => (
                <tr key={s.segment} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                  <td><Badge label={s.segment} /></td>
                  <td className="num text-right text-zinc-400">{usd(s.earned_revenue)}</td>
                  <td className={`num text-right font-medium ${s.margin < 0.3 ? "text-amber-300" : "text-emerald-300"}`}>
                    {(s.margin * 100).toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
    </div>
  );
}
