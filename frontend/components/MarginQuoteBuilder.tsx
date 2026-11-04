"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Spark, Spinner } from "@/components/ui";
import { apiRequest } from "@/lib/api";

/* The equipment-driven margin quote builder (gap B4). Add equipment + labor + materials from the
   catalog, set the target margin, and see the live total, the BLENDED gross margin, and the red
   leak flags ("sell the company, not the box", low-margin lines, excess material, below-sqft).
   Self-contained types (mirrors the /v1/field/* shapes) so it doesn't touch shared lib/types.ts. */

type CatalogItem = {
  code: string;
  name: string;
  kind: "equipment" | "labor" | "material";
  category: string;
  brand: string;
  cost_usd: number;
  price_usd: number;
  margin_pct: number;
  sold_hours: number;
  target_margin_pct: number | null;
};

type PricedLine = {
  code: string;
  name: string;
  kind: string;
  brand: string;
  qty: number;
  sold_hours: number;
  line_price_usd: number;
  line_cost_usd: number;
  margin_pct: number;
  target_margin_pct: number;
  below_target: boolean;
  flags: string[];
};

type MarginFlag = { code: string; line_name: string; message: string };

type MarginQuote = {
  lines: PricedLine[];
  total_price_usd: number;
  total_cost_usd: number;
  gross_profit_usd: number;
  blended_margin_pct: number;
  target_margin_pct: number;
  total_sold_hours: number;
  sqft: number | null;
  sqft_price_per_unit_usd: number | null;
  benchmark_price_usd: number | null;
  flags: MarginFlag[];
  has_blocking_flag: boolean;
};

const usd0 = (n: number | null | undefined) =>
  n == null ? "—" : n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

const pct = (n: number | null | undefined) => (n == null ? "—" : `${n.toFixed(1)}%`);

const KIND_LABEL: Record<string, string> = { equipment: "Equipment", labor: "Labor", material: "Materials" };
const KIND_ORDER = ["equipment", "labor", "material"];

/** Margin → semantic color. Green at/above target, amber within 10pts below, red further below. */
function marginTone(margin: number, target: number): { text: string; ring: string } {
  if (margin >= target) return { text: "text-emerald-300", ring: "border-emerald-400/30 bg-emerald-400/[0.06]" };
  if (margin >= target - 10) return { text: "text-amber-300", ring: "border-amber-400/30 bg-amber-400/[0.06]" };
  return { text: "text-red-300", ring: "border-red-400/40 bg-red-500/[0.08]" };
}

export default function MarginQuoteBuilder({
  token,
  jobLabel,
}: {
  token: string;
  jobLabel?: string | null;
}) {
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [cart, setCart] = useState<Record<string, number>>({});
  const [target, setTarget] = useState(45);
  const [sqft, setSqft] = useState<string>("");
  const [pricePerSqft, setPricePerSqft] = useState<string>("");
  const [quote, setQuote] = useState<MarginQuote | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Load the equipment/labor/material catalog once.
  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      setLoadError(null);
      try {
        const items = await apiRequest<CatalogItem[]>(token, "/v1/field/catalog", "load the equipment catalog");
        if (active) setCatalog(items);
      } catch (e) {
        if (active) setLoadError(e instanceof Error ? e.message : "Couldn't load the catalog.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [token]);

  const repriceFrom = useCallback(
    async (next: Record<string, number>, t: number, sf: string, pps: string) => {
      const lines = Object.entries(next)
        .filter(([, q]) => q > 0)
        .map(([code, qty]) => ({ code, qty }));
      if (lines.length === 0) return setQuote(null);
      const sqftNum = sf.trim() === "" ? null : Math.max(0, Math.round(Number(sf)));
      const ppsNum = pps.trim() === "" ? null : Math.max(0, Number(pps));
      try {
        const q = await apiRequest<MarginQuote>(token, "/v1/field/quote/margin", "price the quote", {
          method: "POST",
          body: JSON.stringify({
            lines,
            target_margin_pct: t,
            sqft: sqftNum && sqftNum > 0 ? sqftNum : null,
            avg_price_per_sqft_usd: ppsNum && ppsNum > 0 ? ppsNum : null,
          }),
        });
        setQuote(q);
      } catch {
        /* transient pricing errors are ignored — the totals just don't update until the next change */
      }
    },
    [token],
  );

  useEffect(() => {
    void repriceFrom(cart, target, sqft, pricePerSqft);
  }, [cart, target, sqft, pricePerSqft, repriceFrom]);

  function step(code: string, delta: number) {
    setCart((c) => {
      const q = Math.max(0, (c[code] ?? 0) + delta);
      const next = { ...c, [code]: q };
      if (q === 0) delete next[code];
      return next;
    });
  }

  const grouped = useMemo(() => {
    const by: Record<string, CatalogItem[]> = {};
    for (const item of catalog) (by[item.kind] ??= []).push(item);
    return KIND_ORDER.filter((k) => by[k]?.length).map((k) => ({ kind: k, items: by[k] }));
  }, [catalog]);

  const blendedTone = quote ? marginTone(quote.blended_margin_pct, quote.target_margin_pct) : null;

  if (loading) {
    return (
      <div className="mt-10 grid place-items-center text-zinc-500">
        <Spinner />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
        {loadError}
      </div>
    );
  }

  if (catalog.length === 0) {
    return (
      <div className="mt-6 rounded-2xl border border-white/[0.07] bg-white/[0.02] px-5 py-10 text-center">
        <div className="mx-auto grid h-10 w-10 place-items-center rounded-xl bg-accent/15 text-accent ring-1 ring-accent/30">
          <Spark />
        </div>
        <p className="mt-3 text-sm font-medium text-zinc-100">Equipment catalog coming soon</p>
        <p className="mt-1 text-xs text-zinc-500">No equipment is configured for this company yet.</p>
      </div>
    );
  }

  return (
    <section className="mt-4">
      {jobLabel && (
        <div className="mb-3 rounded-xl border border-accent/20 bg-accent/[0.06] px-4 py-2.5 text-sm text-zinc-200">
          Margin quote for <span className="font-medium">{jobLabel}</span>
        </div>
      )}

      {/* Target margin + sqft cross-check inputs */}
      <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-4">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-zinc-100">Target margin</label>
          <span className="num text-sm font-semibold text-accent-soft">{target}%</span>
        </div>
        <input
          type="range"
          min={20}
          max={70}
          step={1}
          value={target}
          onChange={(e) => setTarget(Number(e.target.value))}
          className="mt-3 w-full accent-emerald-400"
          aria-label="Target gross margin percent"
        />
        <div className="mt-4 grid grid-cols-2 gap-3">
          <label className="block">
            <span className="text-xs text-zinc-500">Square feet (optional)</span>
            <input
              inputMode="numeric"
              value={sqft}
              onChange={(e) => setSqft(e.target.value.replace(/[^0-9]/g, ""))}
              placeholder="e.g. 1500"
              className="field mt-1 w-full rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2 text-sm text-zinc-100"
            />
          </label>
          <label className="block">
            <span className="text-xs text-zinc-500">Avg $/sqft (cross-check)</span>
            <input
              inputMode="decimal"
              value={pricePerSqft}
              onChange={(e) => setPricePerSqft(e.target.value.replace(/[^0-9.]/g, ""))}
              placeholder="e.g. 6.00"
              className="field mt-1 w-full rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2 text-sm text-zinc-100"
            />
          </label>
        </div>
      </div>

      {/* Flags */}
      {quote && quote.flags.length > 0 && (
        <div className="mt-4 space-y-2">
          {quote.flags.map((f, i) => {
            const soft = f.code === "below_sqft_benchmark";
            return (
              <div
                key={`${f.code}-${i}`}
                className={`flex items-start gap-2.5 rounded-xl border px-4 py-3 text-sm ${
                  soft
                    ? "border-amber-400/30 bg-amber-400/[0.06] text-amber-200"
                    : "border-red-400/40 bg-red-500/[0.08] text-red-200"
                }`}
              >
                <span aria-hidden className="mt-0.5 shrink-0">
                  {soft ? "▲" : "●"}
                </span>
                <span>{f.message}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Catalog by kind with steppers */}
      <div className="mt-4 space-y-5">
        {grouped.map(({ kind, items }) => (
          <div key={kind}>
            <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
              {KIND_LABEL[kind] ?? kind}
            </div>
            <div className="space-y-2">
              {items.map((s) => {
                const q = cart[s.code] ?? 0;
                const lineTarget = s.target_margin_pct ?? target;
                const tone = marginTone(s.margin_pct, lineTarget);
                return (
                  <div
                    key={s.code}
                    className={`flex items-center justify-between rounded-xl border px-4 py-3 ${
                      q > 0 ? "border-accent/30 bg-accent/[0.06]" : "border-white/[0.07] bg-white/[0.02]"
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium text-zinc-100">{s.name}</span>
                        {s.brand && s.brand !== "Standard" && (
                          <span className="shrink-0 rounded-md border border-white/10 bg-white/5 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400">
                            {s.brand}
                          </span>
                        )}
                      </div>
                      <div className="num mt-0.5 text-xs text-zinc-500">
                        {usd0(s.price_usd)}
                        <span className="text-zinc-600"> · cost {usd0(s.cost_usd)}</span>
                        <span className={`ml-1.5 ${tone.text}`}>{pct(s.margin_pct)} GM</span>
                        {s.sold_hours > 0 && <span className="text-zinc-600"> · {s.sold_hours}h</span>}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <button
                        onClick={() => step(s.code, -1)}
                        disabled={q === 0}
                        className="grid h-9 w-9 place-items-center rounded-lg border border-white/10 text-lg text-zinc-300 transition active:scale-95 disabled:opacity-30"
                        aria-label={`Remove one ${s.name}`}
                      >
                        −
                      </button>
                      <span className="num w-5 text-center text-sm text-zinc-100">{q}</span>
                      <button
                        onClick={() => step(s.code, 1)}
                        className="grid h-9 w-9 place-items-center rounded-lg border border-accent/30 bg-accent/10 text-lg text-accent-soft transition active:scale-95"
                        aria-label={`Add one ${s.name}`}
                      >
                        +
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Sticky margin summary bar */}
      {quote && (
        <div className="fixed inset-x-0 bottom-0 z-10 border-t border-white/10 bg-ink-950/95 px-4 py-3 backdrop-blur">
          <div className="mx-auto max-w-md">
            <div className="flex items-end justify-between gap-3">
              <div>
                <div className="num text-xs text-zinc-500">
                  Cost {usd0(quote.total_cost_usd)} · Profit {usd0(quote.gross_profit_usd)}
                </div>
                <div className="num text-2xl font-semibold text-zinc-100">{usd0(quote.total_price_usd)}</div>
              </div>
              <div className={`rounded-xl border px-3 py-2 text-right ${blendedTone?.ring ?? ""}`}>
                <div className="text-[10px] uppercase tracking-wide text-zinc-500">Blended margin</div>
                <div className={`num text-xl font-semibold ${blendedTone?.text ?? "text-zinc-100"}`}>
                  {pct(quote.blended_margin_pct)}
                </div>
              </div>
            </div>
            {quote.sqft && quote.benchmark_price_usd != null && (
              <div className="num mt-1.5 text-[11px] text-zinc-500">
                {usd0(quote.sqft_price_per_unit_usd)}/sqft · benchmark {usd0(quote.benchmark_price_usd)}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
