"use client";

import { Badge, Confidence, Kpi, Panel } from "@/components/ui";
import type { RoutingRunResult } from "@/lib/types";

export default function DispatchView({ data }: { data: RoutingRunResult }) {
  const t = data.totals;
  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Jobs today" value={String(t.jobs)} tone="info" />
        <Kpi label="Assigned" value={`${t.assigned}/${t.jobs}`} tone="ok" />
        <Kpi label="Drive time saved" value={`${t.drive_minutes_saved} min`} tone="ok" />
        <Kpi label="Technicians" value={String(t.techs_used)} tone="neutral" />
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="panel p-5 lg:col-span-3">
          <h2 className="mb-2 text-sm font-semibold text-zinc-100">Dispatch brief</h2>
          <p className="label mb-3">deterministic plan · advisory — a dispatcher accepts it</p>
          <div className="max-h-[260px] overflow-auto whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-300">
            {data.reasoning_logs}
          </div>
        </div>
        <div className="panel p-5 lg:col-span-2">
          <h2 className="mb-4 text-sm font-semibold text-zinc-100">Route optimization</h2>
          <div className="rounded-xl border border-accent/20 bg-accent/[0.07] px-4 py-3">
            <div className="text-xs text-zinc-400">Drive time saved vs. a naive plan</div>
            <div className="num mt-1 text-2xl font-semibold tracking-tight text-accent-soft">{t.drive_minutes_saved} min</div>
            <div className="mt-1 text-[11px] text-zinc-500">
              {t.drive_minutes_optimized} min optimized vs {t.drive_minutes_baseline} min baseline · ~{t.hours_saved}h/day
            </div>
          </div>
        </div>
      </section>

      <Panel title="Suggested assignments" aside={`${data.suggestions.length} stops`}>
        {data.suggestions.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">No jobs to dispatch.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                <th>Customer</th><th>Trade</th><th>Technician</th>
                <th className="text-right">Arrive</th><th className="text-right">Drive</th><th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {data.suggestions.map((s) => (
                <tr key={s.job_id} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                  <td className="font-medium text-zinc-100">{s.customer_name}</td>
                  <td><Badge label={s.trade} /></td>
                  <td className="text-zinc-300">{s.tech_name} <span className="num text-xs text-zinc-600">#{s.sequence}</span></td>
                  <td className="num text-right text-zinc-300">{s.arrival}</td>
                  <td className="num text-right text-zinc-400">{s.drive_minutes}m</td>
                  <td><Confidence value={s.confidence} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      {data.unassigned.length > 0 && (
        <Panel title="Needs a human" aside={`${data.unassigned.length} unassigned`}>
          <table className="w-full text-sm">
            <thead>
              <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                <th>Job</th><th>Trade</th><th>Why</th>
              </tr>
            </thead>
            <tbody>
              {data.unassigned.map((u) => (
                <tr key={u.job_id} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                  <td className="num text-zinc-300">{u.job_id}</td>
                  <td className="text-zinc-400">{u.trade}</td>
                  <td className="text-amber-300">{u.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
    </div>
  );
}
