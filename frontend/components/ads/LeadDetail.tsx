"use client";

import { useCallback, useEffect, useState } from "react";

import { Spinner } from "@/components/ui";
import {
  addLeadActivity,
  getLead,
  type CrmActivity,
  type CrmLead,
} from "@/lib/api";

import { fromCents, timeAgo } from "./format";

// ── ad attribution ──────────────────────────────────────────────────────────────────────────────────
// The lead's source — where it came from — drawn from ad_ref/utm. This is the load-bearing "where did
// this lead come from" panel: it reads platform + campaign/ad ids from ad_ref, and the utm_* params.
function Attribution({ lead }: { lead: CrmLead }) {
  const ad = lead.ad_ref ?? {};
  const utm = lead.utm ?? {};
  const adEntries = Object.entries(ad).filter(([, v]) => v != null && v !== "");
  const utmEntries = Object.entries(utm).filter(([, v]) => v != null && v !== "");
  const platform = ad.platform ?? utm.utm_source ?? null;

  if (adEntries.length === 0 && utmEntries.length === 0) {
    return (
      <p className="text-[13px] text-zinc-500">
        No ad attribution on this lead — captured as <span className="text-zinc-300">{lead.source}</span>.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="label">source</span>
        <span className="inline-flex rounded-md border border-accent/30 bg-accent/10 px-2 py-0.5 text-[11px] font-medium text-accent-soft">
          {platform ?? lead.source}
        </span>
        {ad.show && (
          <span className="inline-flex rounded-md border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] text-zinc-300">
            {ad.show}
          </span>
        )}
      </div>
      {adEntries.length > 0 && (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5 text-[13px]">
          {adEntries.map(([k, v]) => (
            <div key={`ad-${k}`} className="contents">
              <dt className="label self-center">{k.replace(/_/g, " ")}</dt>
              <dd className="num truncate text-zinc-200" title={String(v)}>{String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      {utmEntries.length > 0 && (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5 border-t border-white/[0.06] pt-2.5 text-[13px]">
          {utmEntries.map(([k, v]) => (
            <div key={`utm-${k}`} className="contents">
              <dt className="label self-center">{k.replace(/^utm_/, "").replace(/_/g, " ")}</dt>
              <dd className="num truncate text-zinc-200" title={String(v)}>{String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

const ACTIVITY_ICON: Record<string, string> = {
  note: "📝",
  stage_change: "↗",
  email: "✉️",
  call: "📞",
  booking: "📅",
  system: "⚙️",
};

function Timeline({ activities }: { activities: CrmActivity[] }) {
  if (activities.length === 0) {
    return <p className="text-[13px] text-zinc-500">No activity yet — add the first note below.</p>;
  }
  return (
    <ol className="space-y-3">
      {activities.map((a) => (
        <li key={a.id} className="flex items-start gap-3">
          <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full border border-white/10 bg-white/[0.03] text-[12px]">
            {ACTIVITY_ICON[a.kind] ?? "•"}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[13px] font-medium capitalize text-zinc-200">
                {a.kind.replace(/_/g, " ")}
              </span>
              <span className="label shrink-0" title={a.created_at}>{timeAgo(a.created_at)}</span>
            </div>
            {a.body && <p className="mt-0.5 whitespace-pre-wrap text-[13px] text-zinc-400">{a.body}</p>}
            {a.actor && <p className="mt-0.5 text-[11px] text-zinc-600">by {a.actor}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}

export default function LeadDetail({
  token,
  leadId,
  onClose,
  onChanged,
}: {
  token: string;
  leadId: string;
  /** Close the drawer. */
  onClose: () => void;
  /** Called after an activity is logged so the board can refresh if it wants. */
  onChanged?: () => void;
}) {
  const [lead, setLead] = useState<CrmLead | null>(null);
  const [activities, setActivities] = useState<CrmActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getLead(token, leadId);
      setLead(res.lead);
      setActivities(res.activities);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't open this lead — try again.");
    } finally {
      setLoading(false);
    }
  }, [token, leadId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function logNote() {
    const body = draft.trim();
    if (!body || saving) return;
    setSaving(true);
    setError(null);
    try {
      const activity = await addLeadActivity(token, leadId, body);
      setActivities((a) => [activity, ...a]);
      setDraft("");
      onChanged?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't log that note — try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true">
      <button
        aria-label="Close lead"
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />
      <aside className="relative z-10 flex h-full w-full max-w-md flex-col border-l border-white/[0.08] bg-ink-900 shadow-2xl">
        <header className="flex items-start justify-between gap-3 border-b border-white/[0.06] px-5 py-4">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-zinc-100">
              {lead?.owner ? `Lead · ${lead.owner}` : "Lead"}
            </div>
            <div className="label mt-0.5">
              {lead ? `${lead.stage} · captured ${timeAgo(lead.created_at)}` : "loading…"}
            </div>
          </div>
          <button className="btn-ghost !px-2 !py-1 text-xs" onClick={onClose}>Close</button>
        </header>

        <div className="flex-1 space-y-6 overflow-auto px-5 py-5">
          {error && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-200">
              {error}
              <button className="ml-3 underline underline-offset-2" onClick={() => void load()}>Retry</button>
            </div>
          )}

          {loading && !lead ? (
            <div className="grid place-items-center py-16 text-zinc-500">
              <Spinner />
              <span className="mt-3 text-sm">Loading lead…</span>
            </div>
          ) : lead ? (
            <>
              <section className="grid grid-cols-2 gap-3">
                <div className="kpi">
                  <div className="label">Deal value</div>
                  <div className="num mt-1 text-xl font-semibold text-emerald-300">{fromCents(lead.value_cents)}</div>
                </div>
                <div className="kpi">
                  <div className="label">Stage</div>
                  <div className="mt-1 text-xl font-semibold capitalize text-zinc-100">{lead.stage}</div>
                </div>
              </section>

              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">Ad attribution</h3>
                <Attribution lead={lead} />
              </section>

              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">Activity</h3>
                <Timeline activities={activities} />
              </section>
            </>
          ) : null}
        </div>

        {lead && (
          <footer className="border-t border-white/[0.06] px-5 py-4">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Log a note, call summary, or next step…"
              rows={2}
              className="w-full resize-none rounded-xl border border-white/[0.08] bg-ink-900/70 px-3 py-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-accent/40"
            />
            <div className="mt-2 flex justify-end">
              <button className="btn-primary !px-3 !py-1.5 text-xs" disabled={saving || !draft.trim()} onClick={logNote}>
                {saving ? "Logging…" : "Log note"}
              </button>
            </div>
          </footer>
        )}
      </aside>
    </div>
  );
}
