"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import { Kpi, Panel, Spinner, usd, usd2 } from "@/components/ui";
import {
  getAgentPolicy,
  getPricebookLatest,
  proposePricebookUpdate,
  runPricebook,
} from "@/lib/api";
import type { AgentMode, PricebookItemChange, PricebookRunResult } from "@/lib/types";

// --------------------------------------------------------------------------------------------
// Pricebook re-pricing — mirrors backend/app/agents/pricebook/analytics.py. A vendor cost update flows
// through the sold-hour model (price = sold_hours*rate + materials + materials*markup); we surface the
// old->new price, the margin impact, the SKUs that moved, and flag items beyond the price tolerance.
// --------------------------------------------------------------------------------------------
type RowFilter = "all" | "changed" | "flagged";

function Chip({ children, cls }: { children: ReactNode; cls: string }) {
  return (
    <span className={`inline-flex shrink-0 rounded-md border px-2 py-0.5 text-[11px] font-medium ${cls}`}>
      {children}
    </span>
  );
}

// A +/- delta, color-coded (up = costs/price rose = amber/red; down = green; flat = muted).
function Delta({ usdValue, pct }: { usdValue: number; pct?: number }) {
  const tone =
    usdValue > 0 ? "text-amber-300" : usdValue < 0 ? "text-emerald-300" : "text-zinc-500";
  const sign = usdValue > 0 ? "+" : "";
  return (
    <span className={`num ${tone}`}>
      {usdValue === 0 ? "—" : `${sign}${usd2(usdValue)}`}
      {pct != null && usdValue !== 0 ? (
        <span className="ml-1 text-[11px] opacity-80">
          ({sign}
          {pct.toFixed(1)}%)
        </span>
      ) : null}
    </span>
  );
}

export default function PricebookView({ token }: { token: string }) {
  const [data, setData] = useState<PricebookRunResult | null>(null);
  const [mode, setMode] = useState<AgentMode>("hitl");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const [filter, setFilter] = useState<RowFilter>("changed");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [busyCode, setBusyCode] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [d, p] = await Promise.all([
        getPricebookLatest(token),
        getAgentPolicy(token, "pricebook").catch(() => null),
      ]);
      setData(d);
      if (p) setMode(p.mode);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load the pricebook — try again.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onRun() {
    setLoading(true);
    setError(null);
    setNote(null);
    try {
      setData(await runPricebook(token, true));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't run the pricebook agent — try again.");
    } finally {
      setLoading(false);
    }
  }

  async function applyUpdate(c: PricebookItemChange) {
    if (!data?.run_id) return;
    setBusyCode(c.code);
    setNote(null);
    setError(null);
    try {
      const action = await proposePricebookUpdate(token, data.run_id, c.code);
      if (action.status === "executed") {
        setNote(`Updated ${c.name} — new price ${usd2(c.new_price_usd)} written to the pricebook.`);
        await load();
      } else {
        setNote(
          `Queued the new price for ${c.name} (${usd2(c.new_price_usd)}) — it's awaiting an operator's approval under Agent Controls.`,
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't update that price — try again.");
    } finally {
      setBusyCode(null);
    }
  }

  const rows = useMemo(() => {
    let list = data?.changes ?? [];
    if (filter === "changed") list = list.filter((c) => c.price_delta_usd !== 0);
    else if (filter === "flagged") list = list.filter((c) => c.beyond_tolerance);
    return list; // already sorted largest-move-first by the engine
  }, [data, filter]);

  if (loading && !data) {
    return (
      <div className="panel grid place-items-center px-6 py-16 text-zinc-500">
        <Spinner />
        <span className="mt-3 text-sm">Loading the pricebook…</span>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4">
        {error && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-200">
            {error}
            <button className="ml-3 underline underline-offset-2" onClick={() => void load()}>Retry</button>
          </div>
        )}
        <div className="panel grid place-items-center px-6 py-16 text-center">
          <h2 className="text-lg font-semibold text-zinc-100">No pricebook run yet</h2>
          <p className="mt-1 max-w-md text-sm text-zinc-500">
            Re-price your catalog against the latest vendor cost update — each item&apos;s materials cost
            and price recomputed under your sold-hour model, with the margin impact and what moved.
          </p>
          <button className="btn-primary mt-5" onClick={onRun} disabled={loading}>
            {loading ? <Spinner /> : null}
            {loading ? "Re-pricing…" : "Run the pricebook agent"}
          </button>
        </div>
      </div>
    );
  }

  const t = data.totals;

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-200">
          {error}
          <button className="ml-3 underline underline-offset-2" onClick={() => void load()}>Retry</button>
        </div>
      )}
      {note && <div className="rounded-xl border border-accent/30 bg-accent/10 px-4 py-2.5 text-sm text-accent-soft">{note}</div>}

      {/* Re-pricing header — the impact of the vendor update at a glance. */}
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Kpi label="Items re-priced" value={`${t.items_affected} / ${t.items}`} tone={t.items_affected > 0 ? "warn" : "ok"} />
        <Kpi label="Net price impact" value={usd2(t.total_price_delta_usd)} tone={t.total_price_delta_usd > 0 ? "warn" : "neutral"} />
        <Kpi label="Flagged for review" value={String(t.items_flagged)} tone={t.items_flagged > 0 ? "bad" : "ok"} />
        <Kpi label="Vendor coverage" value={`${t.vendor_coverage_pct.toFixed(0)}%`} tone="neutral" />
        <Kpi label="Avg markup" value={`${t.avg_markup_pct.toFixed(0)}%`} tone="neutral" />
      </section>

      <Panel
        title="Materials & coverage"
        aside={`${t.skus_updated} of ${t.distinct_skus} SKUs updated`}
      >
        <div className="px-5 py-4 text-sm text-zinc-400">
          The latest vendor update covered{" "}
          <span className="num text-zinc-200">{t.skus_updated}</span> of{" "}
          <span className="num text-zinc-200">{t.distinct_skus}</span> distinct SKUs in the catalog.{" "}
          {t.items_affected > 0 ? (
            <>
              It moved <span className="num text-amber-300">{t.items_affected}</span> item price(s) for a net{" "}
              <span className="num text-zinc-200">{usd2(t.total_price_delta_usd)}</span>.
            </>
          ) : (
            <>No currently-priced item used an updated SKU — prices are unchanged.</>
          )}{" "}
          Items moving more than{" "}
          <span className="num text-zinc-200">{data.tolerance_pct.toFixed(0)}%</span> are flagged for a human check.
        </div>
      </Panel>

      <Panel
        title="Re-priced items"
        aside={
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value as RowFilter)}
              className="rounded-md border border-white/10 bg-transparent px-2 py-1 text-xs text-zinc-300"
              aria-label="Filter items"
            >
              <option value="changed">Changed only</option>
              <option value="flagged">Flagged only</option>
              <option value="all">All items</option>
            </select>
          </div>
        }
      >
        {rows.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-zinc-500">
            {filter === "flagged"
              ? "No items moved beyond the tolerance. ✅"
              : (data.changes?.length ?? 0) === 0
                ? "No pricebook items in this run."
                : "No items match this filter."}
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                <th>Item</th>
                <th className="text-right">Old price</th>
                <th className="text-right">New price</th>
                <th className="text-right">Change</th>
                <th className="text-right">Margin Δ</th>
                <th>Drivers</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => {
                const isOpen = expanded === c.code;
                const canApply = c.price_delta_usd !== 0;
                return (
                  <ItemRow
                    key={c.code}
                    c={c}
                    isOpen={isOpen}
                    onToggle={() => setExpanded(isOpen ? null : c.code)}
                    canApply={canApply}
                    applyDisabled={mode === "off"}
                    busy={busyCode === c.code}
                    onApply={() => void applyUpdate(c)}
                  />
                );
              })}
            </tbody>
          </table>
        )}
      </Panel>

      <footer className="flex flex-wrap items-center justify-between gap-2 pt-1 text-xs text-zinc-600">
        <span className="num">
          {data.run_id ? `run ${data.run_id.slice(0, 8)} · ` : ""}inputs {data.inputs_hash.slice(0, 12)} · pricebook from {data.source_system}
        </span>
        <span>
          {mode === "off"
            ? "Pricebook agent is off — turn it on under Agent Controls to write a price."
            : "Advisory — Top Builder AI recomputes; you approve & write the price (always reviewed)."}
        </span>
      </footer>
    </div>
  );
}

// --------------------------------------------------------------------------------------------
// One re-priced item row + its expandable drawer (the bill of materials, before -> after).
// --------------------------------------------------------------------------------------------
function ItemRow({
  c,
  isOpen,
  onToggle,
  canApply,
  applyDisabled,
  busy,
  onApply,
}: {
  c: PricebookItemChange;
  isOpen: boolean;
  onToggle: () => void;
  canApply: boolean;
  applyDisabled: boolean;
  busy: boolean;
  onApply: () => void;
}) {
  return (
    <>
      <tr
        className="cursor-pointer border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02] [&>td]:px-5 [&>td]:py-3"
        onClick={onToggle}
      >
        <td className="font-medium text-zinc-100">
          <span className="mr-1.5 inline-block w-2 text-zinc-500">{isOpen ? "▾" : "▸"}</span>
          {c.name}
          <span className="ml-2 text-[11px] text-zinc-500">{c.code}</span>
          {c.beyond_tolerance && (
            <span className="ml-2">
              <Chip cls="text-red-300 bg-red-500/15 border-red-500/30">⚠ review</Chip>
            </span>
          )}
        </td>
        <td className="num text-right text-zinc-400">{usd2(c.old_price_usd)}</td>
        <td className="num text-right font-medium text-zinc-100">{usd2(c.new_price_usd)}</td>
        <td className="text-right">
          <Delta usdValue={c.price_delta_usd} pct={c.price_delta_pct} />
        </td>
        <td className="text-right">
          <Delta usdValue={c.margin_delta_usd} />
        </td>
        <td className="max-w-[200px] truncate text-[13px] text-zinc-400" title={c.changed_skus.join(", ")}>
          {c.changed_skus.length ? c.changed_skus.join(", ") : "—"}
        </td>
        <td className="text-right" onClick={(e) => e.stopPropagation()}>
          {canApply ? (
            <button
              className="btn-primary !px-3 !py-1 text-xs"
              disabled={busy || applyDisabled}
              title={applyDisabled ? "Pricebook agent is off (Agent Controls)" : "Write the new price to the pricebook"}
              onClick={onApply}
            >
              {busy ? "Updating…" : "Approve & update"}
            </button>
          ) : (
            <span className="text-[11px] text-zinc-600">no change</span>
          )}
        </td>
      </tr>
      {isOpen && (
        <tr className="border-b border-white/[0.04] bg-black/10">
          <td colSpan={7} className="px-5 py-4">
            <ItemDrawer c={c} />
          </td>
        </tr>
      )}
    </>
  );
}

function ItemDrawer({ c }: { c: PricebookItemChange }) {
  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
      {/* The pricing model breakdown. */}
      <div className="lg:col-span-1">
        <div className="label mb-2">Sold-hour pricing</div>
        <dl className="space-y-1.5 text-[13px]">
          <div className="flex justify-between gap-2">
            <dt className="text-zinc-500">Labor ({c.sold_hours}h × {usd(c.sold_hour_rate_usd)})</dt>
            <dd className="num text-zinc-300">{usd2(c.labor_cost_usd)}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-zinc-500">Materials (was → now)</dt>
            <dd className="num text-zinc-300">
              {usd2(c.old_materials_cost_usd)} → {usd2(c.new_materials_cost_usd)}
            </dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-zinc-500">Markup</dt>
            <dd className="num text-zinc-300">{c.markup_pct.toFixed(0)}%</dd>
          </div>
          <div className="mt-1 flex justify-between gap-2 border-t border-white/[0.06] pt-1.5">
            <dt className="text-zinc-400">Price (was → now)</dt>
            <dd className="num font-medium text-zinc-100">
              {usd2(c.old_price_usd)} → {usd2(c.new_price_usd)}
            </dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-zinc-400">Margin (was → now)</dt>
            <dd className="num text-zinc-300">
              {usd2(c.old_margin_usd)} → {usd2(c.new_margin_usd)}
            </dd>
          </div>
        </dl>
      </div>

      {/* The bill of materials, before -> after. */}
      <div className="lg:col-span-2">
        <div className="label mb-2">Bill of materials ({c.lines.length})</div>
        {c.lines.length === 0 ? (
          <p className="text-[13px] text-zinc-500">No materials — labor only.</p>
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="label text-left [&>th]:pb-1.5">
                <th>SKU</th>
                <th className="text-right">Qty</th>
                <th className="text-right">Old cost</th>
                <th className="text-right">New cost</th>
                <th className="text-right">Line Δ</th>
                <th>Vendor</th>
              </tr>
            </thead>
            <tbody>
              {c.lines.map((l) => {
                const lineDelta = l.new_line_cost_usd - l.old_line_cost_usd;
                const changed = l.new_unit_cost_usd !== l.old_unit_cost_usd;
                return (
                  <tr key={l.sku} className={`border-t border-white/[0.04] [&>td]:py-1.5 ${changed ? "" : "opacity-70"}`}>
                    <td className="text-zinc-300">{l.sku}</td>
                    <td className="num text-right text-zinc-400">{l.qty}</td>
                    <td className="num text-right text-zinc-400">{usd2(l.old_unit_cost_usd)}</td>
                    <td className={`num text-right ${changed ? "text-zinc-100" : "text-zinc-400"}`}>{usd2(l.new_unit_cost_usd)}</td>
                    <td className="text-right">
                      <Delta usdValue={lineDelta} />
                    </td>
                    <td className="text-zinc-500">{l.vendor ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
