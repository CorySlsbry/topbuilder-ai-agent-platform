"use client";

import type { ReactNode } from "react";

export const usd = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export const usd2 = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });

export type Tone = "ok" | "warn" | "bad" | "info" | "neutral";

const TONE_CLASS: Record<Tone, string> = {
  ok: "text-emerald-300",
  warn: "text-amber-300",
  bad: "text-red-300",
  info: "text-accent-soft",
  neutral: "text-zinc-100",
};

export function Kpi({ label, value, tone = "neutral" }: { label: string; value: string; tone?: Tone }) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className={`num mt-2 text-2xl font-semibold tracking-tight ${TONE_CLASS[tone]}`}>{value}</div>
    </div>
  );
}

const BADGE_COLORS: Record<string, string> = {
  hvac: "text-[#7ea2ff] bg-[#7ea2ff]/10 border-[#7ea2ff]/20",
  plumbing: "text-[#46d3b6] bg-[#46d3b6]/10 border-[#46d3b6]/20",
  electrical: "text-[#f2b65a] bg-[#f2b65a]/10 border-[#f2b65a]/20",
  install: "text-[#b3a6ff] bg-[#b3a6ff]/10 border-[#b3a6ff]/20",
  controls: "text-[#7ea2ff] bg-[#7ea2ff]/10 border-[#7ea2ff]/20",
  refrigerant: "text-[#46d3b6] bg-[#46d3b6]/10 border-[#46d3b6]/20",
  commercial: "text-[#7ea2ff] bg-[#7ea2ff]/10 border-[#7ea2ff]/20",
  residential: "text-[#46d3b6] bg-[#46d3b6]/10 border-[#46d3b6]/20",
  government: "text-[#f2b65a] bg-[#f2b65a]/10 border-[#f2b65a]/20",
  high: "text-emerald-300 bg-emerald-300/10 border-emerald-300/20",
  standard: "text-zinc-400 bg-white/5 border-white/10",
};

export function Badge({ label }: { label: string }) {
  const cls = BADGE_COLORS[label.toLowerCase()] ?? "text-zinc-300 bg-white/5 border-white/10";
  return (
    <span className={`inline-flex rounded-md border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${cls}`}>
      {label}
    </span>
  );
}

export function Confidence({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-accent" style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="num text-xs text-zinc-400">{value.toFixed(2)}</span>
    </div>
  );
}

export function Panel({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="panel overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-3.5">
        <h2 className="text-sm font-semibold text-zinc-100">{title}</h2>
        {aside ? <span className="label">{aside}</span> : null}
      </div>
      {children}
    </section>
  );
}

export function EmptyState({
  title,
  body,
  busy,
  onRun,
}: {
  title: string;
  body: string;
  busy: boolean;
  onRun: () => void;
}) {
  return (
    <div className="panel mt-6 grid place-items-center px-6 py-16 text-center">
      <div className="grid h-12 w-12 place-items-center rounded-2xl bg-accent/15 text-accent ring-1 ring-accent/30">
        <Spark />
      </div>
      <h2 className="mt-4 text-lg font-semibold text-zinc-100">{title}</h2>
      <p className="mt-1 max-w-sm text-sm text-zinc-500">{body}</p>
      <button className="btn-primary mt-5" onClick={onRun} disabled={busy}>
        {busy ? <Spinner /> : <Spark />}
        {busy ? "Analyzing…" : "Run analysis"}
      </button>
    </div>
  );
}

export function Spark() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 2v6m0 8v6m10-10h-6M8 12H2m15.5-5.5-4 4m-3 3-4 4m11 0-4-4m-3-3-4-4"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function Spinner() {
  return (
    <svg className="animate-spin" width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
