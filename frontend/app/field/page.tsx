"use client";

import { useCallback, useEffect, useState } from "react";

import MarginQuoteBuilder from "@/components/MarginQuoteBuilder";
import { Spark, Spinner, usd } from "@/components/ui";
import { apiRequest, getDevToken } from "@/lib/api";

const TENANTS = [{ slug: "canyonridge", name: "Canyon Ridge Mechanical" }];

type Svc = { code: string; name: string; category: string; unit_price_usd: number; taxable: boolean };
type Job = { id: string; customer_name: string; trade: string; job_type: string; window: string; status: string };
type Quote = {
  lines: { service_code: string; name: string; qty: number; line_total_usd: number }[];
  subtotal_usd: number;
  tax_usd: number;
  total_usd: number;
};

export default function FieldApp() {
  const [token, setToken] = useState<string | null>(null);
  const [tab, setTab] = useState<"jobs" | "quote" | "margin">("jobs");
  const [pricebook, setPricebook] = useState<Svc[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [cart, setCart] = useState<Record<string, number>>({});
  const [quote, setQuote] = useState<Quote | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [submitMsg, setSubmitMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signIn(slug: string) {
    setBusy(true);
    setError(null);
    try {
      const tok = await getDevToken(slug);
      setToken(tok);
      const [pb, js] = await Promise.all([
        apiRequest<Svc[]>(tok, "/v1/field/pricebook", "load the pricebook"),
        apiRequest<Job[]>(tok, "/v1/field/jobs", "load your jobs"),
      ]);
      setPricebook(pb);
      setJobs(js);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  const priceCart = useCallback(
    async (tok: string, next: Record<string, number>) => {
      const line_items = Object.entries(next).filter(([, q]) => q > 0).map(([service_code, qty]) => ({ service_code, qty }));
      if (line_items.length === 0) return setQuote(null);
      try {
        setQuote(await apiRequest<Quote>(tok, "/v1/field/quote", "price the quote", {
          method: "POST", body: JSON.stringify({ line_items, tax_rate: 0.086 }),
        }));
      } catch {
        /* ignore transient pricing errors */
      }
    },
    [],
  );

  useEffect(() => {
    if (token) void priceCart(token, cart);
  }, [token, cart, priceCart]);

  function step(code: string, delta: number) {
    setSubmitMsg(null);
    setCart((c) => {
      const q = Math.max(0, (c[code] ?? 0) + delta);
      const next = { ...c, [code]: q };
      if (q === 0) delete next[code];
      return next;
    });
  }

  async function submit() {
    if (!token || !quote) return;
    setBusy(true);
    setSubmitMsg(null);
    setError(null);
    try {
      const line_items = Object.entries(cart).filter(([, q]) => q > 0).map(([service_code, qty]) => ({ service_code, qty }));
      const action = await apiRequest<{ result: { external_ref?: string } | null; status: string }>(
        token,
        "/v1/field/quote/submit",
        "submit this estimate",
        { method: "POST", body: JSON.stringify({ line_items, tax_rate: 0.086, job_ref: job?.id ?? null }) },
      );
      const ref = action.result?.external_ref;
      setSubmitMsg(action.status === "executed" && ref ? `Estimate created in ServiceTitan (${ref}).` : "Estimate submitted — awaiting approval.");
      setCart({});
    } catch (e) {
      setError(e instanceof Error ? e.message : "Submit failed");
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <main className="mx-auto grid min-h-screen max-w-md place-items-center px-5">
        <div className="panel w-full p-7">
          <div className="grid h-11 w-11 place-items-center rounded-xl bg-accent/15 text-accent ring-1 ring-accent/30"><Spark /></div>
          <h1 className="mt-5 text-xl font-semibold tracking-tight text-zinc-100">Top Builder AI · Field</h1>
          <p className="mt-1 text-sm text-zinc-500">Your jobs and the quote builder, in your pocket.</p>
          <div className="mt-6 space-y-2">
            {TENANTS.map((t) => (
              <button key={t.slug} onClick={() => signIn(t.slug)} disabled={busy}
                className="flex w-full items-center justify-between rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3.5 text-left transition active:scale-[0.99] hover:border-accent/40 disabled:opacity-50">
                <span className="text-sm font-medium text-zinc-100">{t.name}</span>
                <span className="text-zinc-600">→</span>
              </button>
            ))}
          </div>
          {error && <p className="mt-4 text-sm text-red-300">{error}</p>}
        </div>
      </main>
    );
  }

  // iPad/tablet-first: on md+ we drop the tab switcher and show jobs + quote builder side by side
  // (landscape-friendly, larger touch targets); phone keeps the single-column tabbed flow.
  const jobsList = (
    <div className="space-y-2.5">
      {jobs.length === 0 ? (
        <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-6 text-center text-sm text-zinc-500">
          No jobs assigned right now.
        </div>
      ) : (
        jobs.map((j) => {
          const active = job?.id === j.id;
          return (
            <button
              key={j.id}
              onClick={() => { setJob(j); setTab("quote"); }}
              className={`block w-full rounded-2xl border p-4 text-left transition active:scale-[0.99] ${
                active ? "border-accent/40 bg-accent/[0.07]" : "border-white/[0.07] bg-white/[0.02] hover:border-white/15"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="truncate font-medium text-zinc-100">{j.customer_name}</div>
                <span className="shrink-0 rounded-md border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] uppercase tracking-wide text-zinc-400">{j.trade}</span>
              </div>
              <div className="num mt-1 text-xs text-zinc-500">{j.job_type} · {j.window} · {j.status}</div>
            </button>
          );
        })
      )}
    </div>
  );

  const quoteBuilder = (
    <div>
      {job && <div className="mb-3 rounded-xl border border-accent/20 bg-accent/[0.06] px-4 py-2.5 text-sm text-zinc-200">Quote for <span className="font-medium">{job.customer_name}</span></div>}
      {/* one column on phone, two on tablet/landscape so more of the pricebook is reachable */}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-2">
        {pricebook.map((s) => {
          const q = cart[s.code] ?? 0;
          return (
            <div key={s.code} className={`flex items-center justify-between rounded-xl border px-4 py-3 ${q > 0 ? "border-accent/30 bg-accent/[0.06]" : "border-white/[0.07] bg-white/[0.02]"}`}>
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-zinc-100">{s.name}</div>
                <div className="num text-xs text-zinc-500">{usd(s.unit_price_usd)}{s.taxable ? "" : " · no tax"}</div>
              </div>
              <div className="flex items-center gap-3">
                <button onClick={() => step(s.code, -1)} disabled={q === 0} aria-label={`Remove one ${s.name}`} className="grid h-11 w-11 shrink-0 place-items-center rounded-lg border border-white/10 text-xl text-zinc-300 transition active:scale-95 disabled:opacity-30">−</button>
                <span className="num w-5 text-center text-sm text-zinc-100">{q}</span>
                <button onClick={() => step(s.code, 1)} aria-label={`Add one ${s.name}`} className="grid h-11 w-11 shrink-0 place-items-center rounded-lg border border-accent/30 bg-accent/10 text-xl text-accent-soft transition active:scale-95">+</button>
              </div>
            </div>
          );
        })}
      </div>
      {submitMsg && <div className="mt-4 rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-200">{submitMsg}</div>}
    </div>
  );

  return (
    <main className="mx-auto min-h-screen max-w-md px-4 pb-28 pt-5 md:max-w-3xl md:px-6 lg:max-w-5xl md:pb-8">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-accent/15 text-accent ring-1 ring-accent/30"><Spark /></div>
          <div className="text-sm font-semibold text-zinc-100">Field</div>
        </div>
        <button className="btn-ghost text-xs" onClick={() => { setToken(null); setCart({}); setQuote(null); setJob(null); }}>Sign out</button>
      </header>

      {/* Tab switcher — phone only; tablet shows both panes at once */}
      <nav className="mt-4 grid grid-cols-3 gap-1 rounded-xl border border-white/[0.06] bg-ink-900/70 p-1 md:hidden">
        {(["jobs", "quote", "margin"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`rounded-lg py-2.5 text-sm font-medium transition ${t === tab ? "bg-accent/15 text-accent" : "text-zinc-400"}`}>
            {t === "quote" ? "Quote" : t === "margin" ? "Margin" : "Jobs"}
          </button>
        ))}
      </nav>

      {error && <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>}

      {/* Phone: single tabbed pane */}
      <div className="mt-4 md:hidden">
        {tab === "jobs" && jobsList}
        {tab === "quote" && quoteBuilder}
        {tab === "margin" && <MarginQuoteBuilder token={token} jobLabel={job?.customer_name ?? null} />}
      </div>

      {/* Tablet/iPad: jobs rail + quote builder side by side */}
      <div className="mt-5 hidden gap-6 md:grid md:grid-cols-[280px_1fr] lg:grid-cols-[320px_1fr]">
        <section>
          <h2 className="label mb-2 px-1">My jobs</h2>
          {jobsList}
        </section>
        <section>
          <div className="mb-2 flex items-center justify-between px-1">
            <h2 className="label">Quote builder</h2>
            {quote && (
              <div className="num text-sm text-zinc-300">
                <span className="text-zinc-500">Total</span> <span className="font-semibold text-zinc-100">{usd(quote.total_usd)}</span>
              </div>
            )}
          </div>
          {quoteBuilder}
          {quote && (
            <div className="mt-5 flex items-center justify-between rounded-2xl border border-white/10 bg-white/[0.02] px-5 py-4">
              <div>
                <div className="num text-xs text-zinc-500">Subtotal {usd(quote.subtotal_usd)} · Tax {usd(quote.tax_usd)}</div>
                <div className="num text-2xl font-semibold text-zinc-100">{usd(quote.total_usd)}</div>
              </div>
              <button className="btn-primary px-6 py-3 text-base" onClick={submit} disabled={busy}>
                {busy ? <Spinner /> : <Spark />} Submit estimate
              </button>
            </div>
          )}
        </section>
      </div>

      {/* Tablet/iPad: equipment-driven margin builder (full width below the estimate panes) */}
      <section className="mt-8 hidden md:block">
        <div className="mb-2 flex items-center justify-between px-1">
          <h2 className="label">Margin quote builder</h2>
          <span className="text-xs text-zinc-500">Equipment-driven · sell the company, not the box</span>
        </div>
        <div className="mx-auto max-w-md">
          <MarginQuoteBuilder token={token} jobLabel={job?.customer_name ?? null} />
        </div>
      </section>

      {/* Phone: sticky bottom total bar (hidden on tablet — the inline summary above covers it) */}
      {tab === "quote" && quote && (
        <div className="fixed inset-x-0 bottom-0 mx-auto max-w-md border-t border-white/10 bg-ink-950/95 px-4 py-3 backdrop-blur md:hidden">
          <div className="mx-auto flex max-w-md items-center justify-between">
            <div>
              <div className="num text-xs text-zinc-500">Subtotal {usd(quote.subtotal_usd)} · Tax {usd(quote.tax_usd)}</div>
              <div className="num text-xl font-semibold text-zinc-100">{usd(quote.total_usd)}</div>
            </div>
            <button className="btn-primary px-5 py-3" onClick={submit} disabled={busy}>
              {busy ? <Spinner /> : <Spark />} Submit estimate
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
