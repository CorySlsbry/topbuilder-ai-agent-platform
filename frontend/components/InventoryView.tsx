"use client";

import { Fragment, useEffect, useState } from "react";

import { Badge, Confidence, Kpi, Panel, Spinner, usd, usd2 } from "@/components/ui";
import { apiGetOrNull } from "@/lib/api";
import type { InventoryRunResult } from "@/lib/types";

// --- Partial-consumable proration (Alex's metal-spool / copper-coil pain) -----------------------
// Served by a SEPARATE endpoint (GET /v1/agents/inventory/proration/runs/latest) returning a
// ConsumableProrationResult. Typed locally so this view is self-contained; mirrors the backend
// schema in app/agents/inventory/schemas.py exactly.
type JobAllocation = {
  job_id: string;
  allocated_cost_usd: number;
  usage_proxy: number | null;
  share_pct: number;
  reasoning: string;
};
type LotProration = {
  sku: string;
  name: string;
  unit: string;
  method: string;
  total_cost_usd: number;
  total_quantity: number;
  job_count: number;
  dump_job_id: string;
  miscost_corrected_usd: number;
  allocations: JobAllocation[];
  reasoning: string;
  inputs_hash: string;
};
type ConsumableProrationResult = {
  run_id: string | null;
  as_of: string;
  lots: LotProration[];
  totals: { lots_count: number; total_prorated_usd: number; total_miscost_corrected_usd: number };
  reasoning_logs: string;
  inputs_hash: string;
};

const METHOD_LABEL: Record<string, string> = {
  by_usage_proxy: "by usage",
  even: "even split",
  by_job_count: "per job",
};

function ProrationPanel({ token }: { token: string }) {
  const [data, setData] = useState<ConsumableProrationResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setLoading(true);
    apiGetOrNull<ConsumableProrationResult>(
      token,
      "/v1/agents/inventory/proration/runs/latest",
      "load the consumable proration",
    )
      .then((res) => {
        if (live) setData(res);
      })
      .catch((e) => {
        if (live) setError(e instanceof Error ? e.message : "Could not load proration");
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [token]);

  if (loading) {
    return (
      <Panel title="Partial-consumable proration" aside="job-costing accuracy">
        <div className="grid place-items-center px-6 py-10 text-zinc-500">
          <Spinner />
        </div>
      </Panel>
    );
  }
  if (error) {
    return (
      <Panel title="Partial-consumable proration" aside="job-costing accuracy">
        <p className="px-5 py-6 text-sm text-red-300">{error}</p>
      </Panel>
    );
  }
  if (!data || data.lots.length === 0) {
    return (
      <Panel title="Partial-consumable proration" aside="job-costing accuracy">
        <div className="px-5 py-8 text-sm text-zinc-500">
          <p className="text-zinc-300">No proration run yet.</p>
          <p className="mt-1">
            Spools and copper coils get used a little on many jobs but the whole lot lands on the one
            replenish job today. Running proration spreads each lot across the jobs it actually served —
            correcting the job-costing miscost.
          </p>
        </div>
      </Panel>
    );
  }

  const t = data.totals;
  return (
    <div className="space-y-4">
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <Kpi label="Consumable lots prorated" value={String(t.lots_count)} tone="info" />
        <Kpi label="Lot cost reallocated" value={usd(t.total_prorated_usd)} tone="neutral" />
        <Kpi label="Job-costing accuracy gain" value={usd(t.total_miscost_corrected_usd)} tone="ok" />
      </section>

      <Panel
        title="Lots spread across the jobs they served"
        aside={`${data.lots.length} ${data.lots.length === 1 ? "lot" : "lots"}`}
      >
        <table className="w-full text-sm">
          <thead>
            <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
              <th>Consumable</th><th>Method</th><th className="text-right">Lot cost</th>
              <th className="text-right">Jobs</th><th className="text-right">Accuracy gain</th><th />
            </tr>
          </thead>
          <tbody>
            {data.lots.map((lot) => {
              const isOpen = open === lot.sku;
              return (
                <Fragment key={lot.sku}>
                  <tr
                    className="cursor-pointer border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02] [&>td]:px-5 [&>td]:py-3"
                    onClick={() => setOpen(isOpen ? null : lot.sku)}
                  >
                    <td className="font-medium text-zinc-100">
                      {lot.name} <span className="num text-xs text-zinc-600">{lot.sku}</span>
                      <div className="num text-xs text-zinc-500">
                        {lot.total_quantity}
                        {lot.unit} lot · dumped today on {lot.dump_job_id}
                      </div>
                    </td>
                    <td><Badge label={METHOD_LABEL[lot.method] ?? lot.method} /></td>
                    <td className="num text-right text-zinc-300">{usd(lot.total_cost_usd)}</td>
                    <td className="num text-right text-zinc-400">{lot.job_count}</td>
                    <td className="num text-right font-medium text-emerald-300">{usd(lot.miscost_corrected_usd)}</td>
                    <td className="text-right text-zinc-500">{isOpen ? "▾" : "▸"}</td>
                  </tr>
                  {isOpen && (
                    <tr className="border-b border-white/[0.04] last:border-0">
                      <td colSpan={6} className="bg-white/[0.015] px-5 py-3">
                        <p className="mb-3 text-[13px] leading-relaxed text-zinc-400">{lot.reasoning}</p>
                        <div className="label mb-1.5">Per-job allocated material cost</div>
                        <div className="grid grid-cols-1 gap-1.5 md:grid-cols-2">
                          {lot.allocations.map((a) => (
                            <div
                              key={a.job_id}
                              className="flex items-center justify-between rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2"
                            >
                              <span className="num text-xs text-zinc-300">
                                {a.job_id}
                                {a.usage_proxy !== null && (
                                  <span className="text-zinc-600"> · {a.usage_proxy}{lot.unit}</span>
                                )}
                              </span>
                              <span className="flex items-center gap-2">
                                <span className="num text-xs text-zinc-500">{a.share_pct}%</span>
                                <span className="num text-sm font-medium text-zinc-100">{usd(a.allocated_cost_usd)}</span>
                              </span>
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}

function RecoveryBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.max(3, Math.round((value / max) * 100)) : 0;
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-xs text-zinc-400">{label}</span>
        <span className="num text-sm font-medium text-zinc-100">{usd(value)}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/5">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

export default function InventoryView({ data, token }: { data: InventoryRunResult; token?: string }) {
  const t = data.totals;
  const recoverableNow = t.total_shrinkage_usd + t.total_unbilled_usd;
  const recovMax = Math.max(t.total_shrinkage_usd, t.total_unbilled_usd, t.total_arbitrage_annual_usd, 1);
  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Parts to reorder" value={String(t.reorders_count)} tone={t.reorders_count ? "warn" : "ok"} />
        <Kpi label="Stockout exposure" value={usd(t.total_stockout_exposure_usd)} tone="warn" />
        <Kpi label="Recoverable now" value={usd(recoverableNow)} tone="bad" />
        <Kpi label="Arbitrage / year" value={usd(t.total_arbitrage_annual_usd)} tone="info" />
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="panel p-5 lg:col-span-3">
          <h2 className="mb-2 text-sm font-semibold text-zinc-100">Supply-chain narrative</h2>
          <p className="label mb-3">deterministic figures · LLM/template narration</p>
          <div className="max-h-[260px] overflow-auto whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-300">
            {data.reasoning_logs}
          </div>
        </div>
        <div className="panel p-5 lg:col-span-2">
          <h2 className="mb-4 text-sm font-semibold text-zinc-100">Value recovery</h2>
          <div className="space-y-4">
            <RecoveryBar label="Truck-stock shrinkage" value={t.total_shrinkage_usd} max={recovMax} color="#f2606a" />
            <RecoveryBar label="Unbilled materials" value={t.total_unbilled_usd} max={recovMax} color="#f2b65a" />
            <RecoveryBar label="Vendor arbitrage (annual)" value={t.total_arbitrage_annual_usd} max={recovMax} color="#46d3b6" />
          </div>
        </div>
      </section>

      <Panel title="Critical reorders" aside={`${data.critical_reorders.length} parts`}>
        {data.critical_reorders.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">Stock levels are healthy.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                <th>Part</th><th>Class</th><th className="text-right">Days to stockout</th>
                <th className="text-right">Order qty</th><th className="text-right">Exposure</th><th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {data.critical_reorders.map((r) => (
                <tr key={r.sku} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                  <td className="font-medium text-zinc-100">{r.name} <span className="num text-xs text-zinc-600">{r.sku}</span></td>
                  <td><Badge label={r.margin_class} /></td>
                  <td className="num text-right text-amber-300">{r.days_to_stockout === null ? "—" : `${r.days_to_stockout.toFixed(1)}d`}</td>
                  <td className="num text-right text-zinc-300">{r.recommended_order_qty}</td>
                  <td className="num text-right font-medium text-zinc-100">{usd(r.stockout_exposure_usd)}</td>
                  <td><Confidence value={r.confidence} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Panel title="Truck-stock shrinkage" aside={`${data.shrinkage_alerts.length} alerts`}>
          {data.shrinkage_alerts.length === 0 ? (
            <p className="px-5 py-6 text-sm text-zinc-500">No variances over threshold.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                  <th>Truck</th><th>Part</th><th className="text-right">Short</th><th className="text-right">Value</th>
                </tr>
              </thead>
              <tbody>
                {data.shrinkage_alerts.map((s) => (
                  <tr key={`${s.technician_id}-${s.sku}`} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                    <td className="num text-zinc-300">{s.technician_id}</td>
                    <td className="text-zinc-100">{s.name}</td>
                    <td className="num text-right text-zinc-400">{s.variance}</td>
                    <td className="num text-right font-medium text-red-300">{usd(s.shrinkage_value_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <Panel title="Unbilled materials" aside={`${data.unbilled_materials.length} items`}>
          {data.unbilled_materials.length === 0 ? (
            <p className="px-5 py-6 text-sm text-zinc-500">Everything is billed.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                  <th>Job</th><th>Part</th><th className="text-right">Qty</th><th className="text-right">At risk</th>
                </tr>
              </thead>
              <tbody>
                {data.unbilled_materials.map((u) => (
                  <tr key={`${u.job_id}-${u.sku}`} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                    <td className="num text-zinc-300">{u.job_id}</td>
                    <td className="text-zinc-100">{u.name}</td>
                    <td className="num text-right text-zinc-400">{u.qty_used}</td>
                    <td className="num text-right font-medium text-amber-300">{usd(u.unbilled_value_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      <Panel title="Vendor arbitrage" aside={`${data.vendor_arbitrage.length} opportunities`}>
        {data.vendor_arbitrage.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">No cheaper vendor found.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                <th>Part</th><th className="text-right">Current</th><th>Best vendor</th>
                <th className="text-right">Their price</th><th className="text-right">Annual savings</th>
              </tr>
            </thead>
            <tbody>
              {data.vendor_arbitrage.map((o) => (
                <tr key={o.sku} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                  <td className="font-medium text-zinc-100">{o.name}</td>
                  <td className="num text-right text-zinc-400">{usd2(o.current_unit_cost)}</td>
                  <td className="text-zinc-300">{o.best_vendor}</td>
                  <td className="num text-right text-emerald-300">{usd2(o.best_unit_price)}</td>
                  <td className="num text-right font-medium text-emerald-300">{usd(o.annual_savings_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      {/* Partial-consumable proration — loads its own run from the dedicated endpoint when a token
          is available (the dashboard passes one). */}
      {token && <ProrationPanel token={token} />}
    </div>
  );
}
