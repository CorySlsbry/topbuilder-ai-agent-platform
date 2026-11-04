"use client";

import { Badge, Kpi, Panel, usd } from "@/components/ui";
import type { DocumentsRunResult } from "@/lib/types";

// --- PO/AP-from-email + warranty-registration lanes -------------------------------------------
// These ride on the same Documents run result (backend app/agents/documents/schemas.py:
// `accounts_payable` + `warranty`). Typed locally so the view is self-contained until the shared
// DocumentsRunResult type carries them; mirrors the backend schema exactly.
type ApDraft = {
  bill_id: string;
  vendor: string;
  doc_number: string;
  amount_usd: number;
  job_ref: string;
  job_name: string;
  customer_name: string;
  confidence: number;
  action: string;
  reasoning: string;
};
type UnmatchedBill = {
  bill_id: string;
  vendor: string;
  doc_number: string;
  amount_usd: number;
  extracted_job_ref: string | null;
  job_ref_source: string;
  reason: string;
};
type ApSection = {
  drafts: ApDraft[];
  needs_human: UnmatchedBill[];
  totals: {
    bills_processed: number;
    auto_proposed: number;
    needs_human: number;
    auto_value_usd: number;
    needs_human_value_usd: number;
  };
};
type WarrantyPacket = {
  equipment_id: string;
  job_ref: string;
  customer_name: string;
  brand: string;
  model: string;
  serial: string;
  portal: string;
  fields: Record<string, string>;
  confidence: number;
  reasoning: string;
};
type WarrantyException = { equipment_id: string; job_ref: string; brand: string; reason: string };
type WarrantySection = {
  packets: WarrantyPacket[];
  needs_human: WarrantyException[];
  totals: { equipment_processed: number; packets_ready: number; needs_human: number };
};
type DocumentsRunResultExt = DocumentsRunResult & {
  accounts_payable?: ApSection | null;
  warranty?: WarrantySection | null;
};

const ACTION_PILL: Record<string, string> = {
  file: "text-emerald-300 bg-emerald-300/10 border-emerald-300/20",
  expiring: "text-amber-300 bg-amber-300/10 border-amber-300/20",
  needs_signature: "text-accent-soft bg-accent/10 border-accent/25",
};

function ActionPill({ action }: { action: string }) {
  const cls = ACTION_PILL[action] ?? "text-zinc-300 bg-white/5 border-white/10";
  const label = action === "needs_signature" ? "e-sign" : action;
  return (
    <span className={`inline-flex rounded-md border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${cls}`}>
      {label}
    </span>
  );
}

export default function DocumentsView({ data }: { data: DocumentsRunResult }) {
  const t = data.totals;
  const ap = (data as DocumentsRunResultExt).accounts_payable ?? null;
  const warranty = (data as DocumentsRunResultExt).warranty ?? null;
  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Processed" value={String(t.documents_processed)} tone="info" />
        <Kpi label="Auto-filed" value={String(t.auto_filed)} tone="ok" />
        <Kpi label="Needs signature" value={String(t.needs_signature)} tone="warn" />
        <Kpi label="Extracted value" value={usd(t.extracted_value_usd)} tone="neutral" />
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="panel p-5 lg:col-span-3">
          <h2 className="mb-2 text-sm font-semibold text-zinc-100">Document operations brief</h2>
          <p className="label mb-3">deterministic classify + route · filing is human-approved</p>
          <div className="max-h-[260px] overflow-auto whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-300">
            {data.reasoning_logs}
          </div>
        </div>
        <div className="panel p-5 lg:col-span-2">
          <h2 className="mb-4 text-sm font-semibold text-zinc-100">Exceptions</h2>
          <div className="space-y-3">
            <div className="rounded-xl border border-amber-300/20 bg-amber-300/[0.07] px-4 py-3">
              <div className="text-xs text-zinc-400">Insurance COIs expiring (≤30 days)</div>
              <div className="num mt-1 text-2xl font-semibold text-amber-300">{t.expiring_soon}</div>
            </div>
            <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] px-4 py-3">
              <div className="text-xs text-zinc-400">Needs a human</div>
              <div className="num mt-1 text-2xl font-semibold text-zinc-100">{t.needs_human}</div>
            </div>
          </div>
        </div>
      </section>

      <Panel title="Filing plan — proposed (each routes to a customer + ServiceTitan folder)" aside={`${data.filings.length} documents`}>
        <table className="w-full text-sm">
          <thead>
            <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
              <th>Document</th><th>Type</th><th>Customer</th><th>Files to</th>
              <th className="text-right">Amount</th><th>Action</th>
            </tr>
          </thead>
          <tbody>
            {data.filings.map((f) => (
              <tr key={f.doc_id} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                <td className="font-medium text-zinc-100">{f.filename}</td>
                <td><Badge label={f.doc_type.replace("_", " ")} /></td>
                <td className="text-zinc-300">{f.customer_name}</td>
                <td className="num text-zinc-400">{f.department}/{f.st_folder}</td>
                <td className="num text-right text-zinc-300">{f.amount_usd === null ? "—" : usd(f.amount_usd)}</td>
                <td><ActionPill action={f.action} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      {data.needs_human.length > 0 && (
        <Panel title="Needs a human" aside={`${data.needs_human.length} exceptions`}>
          <table className="w-full text-sm">
            <thead>
              <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                <th>Document</th><th>Type</th><th>Why</th>
              </tr>
            </thead>
            <tbody>
              {data.needs_human.map((u) => (
                <tr key={u.doc_id} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                  <td className="text-zinc-100">{u.filename}</td>
                  <td className="text-zinc-400">{u.doc_type}</td>
                  <td className="text-amber-300">{u.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}

      {/* PO / AP from emailed bills — the agent attaches the bill + drafts the A/P entry against the
          job number; humans handle missing/handwritten job numbers. */}
      {ap && (
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-zinc-100">Accounts payable — from emailed bills</h2>
            <span className="label">draft to ServiceTitan · human-approved</span>
          </div>
          <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Kpi label="Bills processed" value={String(ap.totals.bills_processed)} tone="info" />
            <Kpi label="A/P drafts ready" value={String(ap.totals.auto_proposed)} tone="ok" />
            <Kpi label="Drafted value" value={usd(ap.totals.auto_value_usd)} tone="neutral" />
            <Kpi label="Needs a human" value={String(ap.totals.needs_human)} tone={ap.totals.needs_human ? "warn" : "ok"} />
          </section>

          <Panel title="A/P draft worklist — matched to a job" aside={`${ap.drafts.length} drafts`}>
            {ap.drafts.length === 0 ? (
              <p className="px-5 py-6 text-sm text-zinc-500">No bills auto-matched this run.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                    <th>Vendor</th><th>Bill #</th><th>Job</th><th>Customer</th>
                    <th className="text-right">Amount</th><th>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {ap.drafts.map((d) => (
                    <tr key={d.bill_id} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                      <td className="font-medium text-zinc-100">{d.vendor}</td>
                      <td className="num text-zinc-400">{d.doc_number}</td>
                      <td className="num text-zinc-300">{d.job_ref}<span className="text-zinc-600"> {d.job_name}</span></td>
                      <td className="text-zinc-300">{d.customer_name}</td>
                      <td className="num text-right font-medium text-zinc-100">{usd(d.amount_usd)}</td>
                      <td className="num text-zinc-400">{Math.round(d.confidence * 100)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>

          {ap.needs_human.length > 0 && (
            <Panel title="Bills that need a human" aside={`${ap.needs_human.length} · ${usd(ap.totals.needs_human_value_usd)}`}>
              <table className="w-full text-sm">
                <thead>
                  <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                    <th>Vendor</th><th>Bill #</th><th className="text-right">Amount</th><th>Job # source</th><th>Why</th>
                  </tr>
                </thead>
                <tbody>
                  {ap.needs_human.map((b) => (
                    <tr key={b.bill_id} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                      <td className="text-zinc-100">{b.vendor}</td>
                      <td className="num text-zinc-400">{b.doc_number}</td>
                      <td className="num text-right text-zinc-300">{usd(b.amount_usd)}</td>
                      <td className="text-zinc-400">{b.extracted_job_ref ?? "—"} <span className="text-zinc-600">({b.job_ref_source})</span></td>
                      <td className="text-amber-300">{b.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}
        </section>
      )}

      {/* Warranty registration — the agent assembles the per-vendor registration packet (serial photo
          → fields). A human must log into each vendor portal first (agents never sign in). */}
      {warranty && (
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-zinc-100">Warranty registration</h2>
            <span className="label">packet ready · needs a human login</span>
          </div>
          <section className="grid grid-cols-2 gap-4 lg:grid-cols-3">
            <Kpi label="Equipment processed" value={String(warranty.totals.equipment_processed)} tone="info" />
            <Kpi label="Packets ready" value={String(warranty.totals.packets_ready)} tone="ok" />
            <Kpi label="Needs a human" value={String(warranty.totals.needs_human)} tone={warranty.totals.needs_human ? "warn" : "ok"} />
          </section>

          {warranty.packets.length > 0 && (
            <Panel title="Registration packets — ready to submit on each vendor portal" aside={`${warranty.packets.length} packets`}>
              <div className="rounded-t-none border-b border-amber-300/15 bg-amber-300/[0.06] px-5 py-2.5 text-[12px] text-amber-200/90">
                The agent fills the form after a human signs into the vendor portal — agents never sign in themselves.
              </div>
              <div className="divide-y divide-white/[0.05]">
                {warranty.packets.map((p) => (
                  <div key={p.equipment_id} className="px-5 py-3.5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="font-medium text-zinc-100">
                        {p.brand} {p.model} <span className="num text-xs text-zinc-500">SN {p.serial}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="rounded-md border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] text-zinc-400">{p.portal}</span>
                        <span className="num text-[11px] text-zinc-500">{Math.round(p.confidence * 100)}%</span>
                      </div>
                    </div>
                    <div className="num mt-1 text-xs text-zinc-500">{p.customer_name} · job {p.job_ref}</div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {Object.entries(p.fields).map(([k, v]) => (
                        <span key={k} className="inline-flex rounded-md border border-white/10 bg-white/[0.03] px-2 py-0.5 text-[11px] text-zinc-400">
                          <span className="text-zinc-500">{k.replace(/_/g, " ")}:</span>&nbsp;<span className="text-zinc-300">{v}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
          )}

          {warranty.needs_human.length > 0 && (
            <Panel title="Warranty exceptions" aside={`${warranty.needs_human.length}`}>
              <table className="w-full text-sm">
                <thead>
                  <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                    <th>Equipment</th><th>Brand</th><th>Job</th><th>Why</th>
                  </tr>
                </thead>
                <tbody>
                  {warranty.needs_human.map((x) => (
                    <tr key={x.equipment_id} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                      <td className="num text-zinc-300">{x.equipment_id}</td>
                      <td className="text-zinc-100">{x.brand}</td>
                      <td className="num text-zinc-400">{x.job_ref}</td>
                      <td className="text-amber-300">{x.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}
        </section>
      )}
    </div>
  );
}
