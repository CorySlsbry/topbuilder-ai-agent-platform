"use client";

import { useMemo, useState } from "react";

import { shortDate } from "@/components/chartKit";
import { Badge, Kpi, Panel, usd } from "@/components/ui";
// Single source of truth — the triage contract mirrors backend routing/schemas.TriageRunResult.
import type { BoardDay, TriagedJob, TriageRunResult } from "@/lib/types";

// Priority palette: P1 emergency = red, P2 same-day = amber, P3 flexible = zinc.
const PRIORITY: Record<number, { label: string; chip: string; dot: string }> = {
  1: { label: "P1", chip: "border-red-500/40 bg-red-500/10 text-red-300", dot: "bg-red-400" },
  2: { label: "P2", chip: "border-amber-500/40 bg-amber-500/10 text-amber-300", dot: "bg-amber-400" },
  3: { label: "P3", chip: "border-white/15 bg-white/[0.04] text-zinc-400", dot: "bg-zinc-500" },
};

function PriorityTag({ priority, label }: { priority: number; label: string }) {
  const p = PRIORITY[priority] ?? PRIORITY[3];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-semibold ${p.chip}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${p.dot}`} />
      {p.label}
      <span className="font-normal opacity-70">· {label}</span>
    </span>
  );
}

/** Capacity-vs-booked read for one board day. utilization colors the bar; over-capacity overflows red. */
function BoardDayCard({ d }: { d: BoardDay }) {
  const over = d.over_capacity_minutes > 0;
  const util = d.utilization_pct;
  // Within-capacity fill up to 100%, then an overflow segment for the part over capacity.
  const fill = Math.min(100, util);
  const barColor = over ? "#f87171" : util >= 85 ? "#f2b65a" : "#46d3b6";
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
      <div className="flex items-baseline justify-between">
        <div className="text-sm font-semibold text-zinc-100">{shortDate(d.day)}</div>
        <div className="num text-xs text-zinc-500">
          {d.job_count} job{d.job_count === 1 ? "" : "s"}
        </div>
      </div>
      <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-white/[0.06]">
        <div className="h-full rounded-full transition-all" style={{ width: `${fill}%`, backgroundColor: barColor }} />
      </div>
      <div className="mt-2 flex items-baseline justify-between">
        <span className={`num text-sm font-semibold ${over ? "text-red-300" : "text-zinc-100"}`}>{util}%</span>
        <span className="num text-[11px] text-zinc-500">
          {over ? (
            <span className="text-red-300">{Math.round(d.over_capacity_minutes / 60)}h over</span>
          ) : (
            `${Math.round(d.free_minutes / 60)}h free`
          )}
        </span>
      </div>
      <div className="num mt-1 text-[11px] text-zinc-600">
        {Math.round(d.booked_minutes / 60)}h booked / {Math.round(d.capacity_minutes / 60)}h capacity
      </div>
      {d.unavailable_tech_ids.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1" title="Technicians with no shift this day (unavailable)">
          {d.unavailable_tech_ids.map((id) => (
            <span key={id} className="rounded border border-white/[0.06] bg-white/[0.03] px-1.5 py-px text-[10px] text-zinc-600 line-through">
              {id}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function JobRow({ job }: { job: TriagedJob }) {
  const top = job.candidates[0];
  return (
    <div className="px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <PriorityTag priority={job.priority} label={job.priority_label} />
            <span className="font-medium text-zinc-100">{job.customer_name}</span>
            <Badge label={job.trade} />
            <span className="text-xs text-zinc-500">{job.job_type}</span>
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-zinc-500">{job.reason}</p>
        </div>
        <div className="num shrink-0 text-right text-sm font-semibold text-zinc-100">{usd(job.revenue)}</div>
      </div>

      {job.assignable && top ? (
        <div className="mt-3 flex flex-wrap items-center gap-3 rounded-lg border border-accent/20 bg-accent/[0.06] px-3 py-2">
          <div className="text-xs">
            <span className="label">Recommended</span>
            <div className="mt-0.5 font-medium text-accent-soft">{job.recommended_tech_name}</div>
          </div>
          <div className="ml-auto flex items-center gap-4 text-[11px] text-zinc-400">
            <span className="num" title="Drive time">{top.drive_minutes}m drive</span>
            <span className="num" title="Average ticket">{usd(top.avg_ticket)} avg</span>
            <span className="num" title="Conversion / close rate">{top.conversion_pct}% close</span>
            <span className="num font-semibold text-zinc-200" title="Overall rank score (skill + proximity + revenue)">
              {top.score}/100
            </span>
          </div>
        </div>
      ) : (
        <div className="mt-3 rounded-lg border border-amber-500/25 bg-amber-500/[0.07] px-3 py-2 text-xs text-amber-300">
          Needs a human — {job.reason}
        </div>
      )}
    </div>
  );
}

type Filter = "all" | 1 | 2 | 3;

export default function DispatchBoardView({ data }: { data: TriageRunResult }) {
  const t = data.totals;
  const [filter, setFilter] = useState<Filter>("all");

  // The engine already orders P1 -> P3 (then revenue desc); keep that order, just filter.
  const jobs = useMemo(
    () => (filter === "all" ? data.triaged : data.triaged.filter((j) => j.priority === filter)),
    [data.triaged, filter],
  );

  const FILTERS: { key: Filter; label: string; count: number }[] = [
    { key: "all", label: "All", count: t.jobs },
    { key: 1, label: "P1", count: t.p1 },
    { key: 2, label: "P2", count: t.p2 },
    { key: 3, label: "P3", count: t.p3 },
  ];

  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Kpi label="Jobs to triage" value={String(t.jobs)} tone="info" />
        <Kpi label="P1 emergency" value={String(t.p1)} tone={t.p1 ? "bad" : "ok"} />
        <Kpi label="P2 same-day" value={String(t.p2)} tone={t.p2 ? "warn" : "ok"} />
        <Kpi label="Auto-assignable" value={`${t.assignable}/${t.jobs}`} tone="ok" />
        <Kpi label="Needs a human" value={String(t.needs_human)} tone={t.needs_human ? "warn" : "ok"} />
      </section>

      {/* ---- 3-day call board ---- */}
      <Panel title="Next 3 days" aside="capacity vs booked">
        <div className="p-4">
          {data.board.length === 0 ? (
            <p className="px-1 py-6 text-center text-sm text-zinc-500">No board data for this run.</p>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {data.board.map((d) => (
                <BoardDayCard key={d.day} d={d} />
              ))}
            </div>
          )}
        </div>
      </Panel>

      {/* ---- the unassigned queue, ordered P1 -> P3 ---- */}
      <Panel
        title="Unassigned queue"
        aside={
          <div className="flex items-center gap-1">
            {FILTERS.map((f) => (
              <button
                key={String(f.key)}
                onClick={() => setFilter(f.key)}
                className={`rounded-md px-2 py-0.5 text-[11px] font-medium transition ${
                  filter === f.key ? "bg-accent/20 text-accent" : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {f.label} {f.count}
              </button>
            ))}
          </div>
        }
      >
        {jobs.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-zinc-500">
            {data.triaged.length === 0 ? "Nothing in the queue — every job is dispatched." : "No jobs at this priority."}
          </p>
        ) : (
          <div className="divide-y divide-white/[0.05]">
            {jobs.map((job) => (
              <JobRow key={job.job_id} job={job} />
            ))}
          </div>
        )}
      </Panel>

      <div className="panel p-5">
        <h2 className="mb-2 text-sm font-semibold text-zinc-100">Triage brief</h2>
        <p className="label mb-3">deterministic priority + revenue rank · advisory — the dispatcher accepts or overrides</p>
        <div className="max-h-[260px] overflow-auto whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-300">
          {data.reasoning_logs || "No narrative for this run."}
        </div>
      </div>
    </div>
  );
}
