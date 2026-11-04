"use client";

import { Badge, Confidence, Kpi, Panel, usd } from "@/components/ui";
import type { BookingRunResult, ProposedBooking, UnbookedIntake } from "@/lib/types";

const URGENCY_CLASS: Record<string, string> = {
  emergency: "text-red-300 bg-red-300/10 border-red-300/20",
  same_day: "text-amber-300 bg-amber-300/10 border-amber-300/20",
  routine: "text-zinc-400 bg-white/5 border-white/10",
};

function Urgency({ value }: { value: string }) {
  const cls = URGENCY_CLASS[value] ?? "text-zinc-300 bg-white/5 border-white/10";
  return (
    <span className={`inline-flex rounded-md border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${cls}`}>
      {value.replace("_", "-")}
    </span>
  );
}

function FunnelRow({ label, value, pct, tone }: { label: string; value: number; pct: number; tone: string }) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-xs text-zinc-400">{label}</span>
        <span className="num text-sm font-medium text-zinc-100">{value}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/5">
        <div className="h-full rounded-full" style={{ width: `${Math.max(3, pct)}%`, background: tone }} />
      </div>
    </div>
  );
}

export default function BookingView({ data }: { data: BookingRunResult }) {
  const t = data.totals;
  const received = Math.max(t.intakes_received, 1);
  const afterHoursShare =
    t.recovered_revenue_usd > 0 ? Math.round((t.after_hours_recovered_usd / t.recovered_revenue_usd) * 100) : 0;

  // No open slot in a trade booked solid -> a human (dispatcher) should act now.
  const needsHuman = data.unbooked.filter((u: UnbookedIntake) => /availabilit/i.test(u.reason));
  const screened = data.unbooked.filter((u: UnbookedIntake) => !/availabilit/i.test(u.reason));

  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Calls handled 24/7" value={String(t.intakes_received)} tone="info" />
        <Kpi label="Jobs booked" value={String(t.proposed_bookings)} tone="ok" />
        <Kpi label="Revenue recovered" value={usd(t.recovered_revenue_usd)} tone="ok" />
        <Kpi label="After-hours recovered" value={usd(t.after_hours_recovered_usd)} tone="info" />
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="panel p-5 lg:col-span-3">
          <h2 className="mb-2 text-sm font-semibold text-zinc-100">Front-desk narrative</h2>
          <p className="label mb-3">deterministic figures · LLM/template narration</p>
          <div className="max-h-[260px] overflow-auto whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-300">
            {data.reasoning_logs}
          </div>
        </div>
        <div className="panel p-5 lg:col-span-2">
          <h2 className="mb-4 text-sm font-semibold text-zinc-100">Intake funnel</h2>
          <div className="space-y-4">
            <FunnelRow label="Calls handled" value={t.intakes_received} pct={100} tone="#7ea2ff" />
            <FunnelRow label="Qualified leads" value={t.qualified} pct={(t.qualified / received) * 100} tone="#9b8cff" />
            <FunnelRow label="Jobs booked" value={t.proposed_bookings} pct={(t.proposed_bookings / received) * 100} tone="#46d3b6" />
          </div>
          <div className="mt-5 rounded-xl border border-accent/20 bg-accent/[0.07] px-4 py-3">
            <div className="text-xs text-zinc-400">After-hours revenue recovered</div>
            <div className="num mt-1 text-2xl font-semibold tracking-tight text-accent-soft">
              {usd(t.after_hours_recovered_usd)}
            </div>
            <div className="mt-1 text-[11px] text-zinc-500">
              {t.after_hours_captured} job(s) booked off after-hours calls · {afterHoursShare}% of recovered revenue
            </div>
          </div>
        </div>
      </section>

      <Panel title="Proposed bookings" aside={`${data.proposed_bookings.length} · awaiting dispatch confirm`}>
        {data.proposed_bookings.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">No bookable intakes in this batch.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                <th>Caller</th><th>Trade</th><th>Urgency</th><th>Window</th>
                <th className="text-right">Est. value</th><th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {data.proposed_bookings.map((b: ProposedBooking) => (
                <tr key={b.intake_id} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                  <td className="font-medium text-zinc-100">
                    {b.caller_name ?? "Unknown caller"}
                    {b.after_hours && (
                      <span className="ml-2 rounded border border-accent/25 bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-accent-soft">
                        after hrs
                      </span>
                    )}
                    {b.job_type && <span className="num ml-2 text-xs text-zinc-600">{b.job_type}</span>}
                  </td>
                  <td><Badge label={b.trade} /></td>
                  <td><Urgency value={b.urgency} /></td>
                  <td className="num text-zinc-300">{b.proposed_date}</td>
                  <td className="num text-right font-medium text-emerald-300">{usd(b.estimated_value_usd)}</td>
                  <td><Confidence value={b.confidence} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Panel title="Needs a dispatcher now" aside={`${needsHuman.length} qualified · no open slot`}>
          {needsHuman.length === 0 ? (
            <p className="px-5 py-6 text-sm text-zinc-500">Every qualified lead found an open slot.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                  <th>Intake</th><th>Trade</th><th>Why</th>
                </tr>
              </thead>
              <tbody>
                {needsHuman.map((u: UnbookedIntake) => (
                  <tr key={u.intake_id} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                    <td className="num text-zinc-300">{u.intake_id}</td>
                    <td><Badge label={u.trade} /></td>
                    <td className="text-amber-300">{u.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <Panel title="Screened out" aside={`${screened.length} non-jobs filtered`}>
          {screened.length === 0 ? (
            <p className="px-5 py-6 text-sm text-zinc-500">Nothing to screen — every call was a real lead.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                  <th>Intake</th><th>Trade</th><th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {screened.map((u: UnbookedIntake) => (
                  <tr key={u.intake_id} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                    <td className="num text-zinc-300">{u.intake_id}</td>
                    <td className="text-zinc-400">{u.trade}</td>
                    <td className="text-zinc-500">{u.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>
    </div>
  );
}
