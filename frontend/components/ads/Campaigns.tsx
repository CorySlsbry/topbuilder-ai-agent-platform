"use client";

import { useCallback, useEffect, useState } from "react";

import { Panel, Spinner } from "@/components/ui";
import {
  approveAndExecuteAction,
  buildCampaign,
  listAdAccounts,
  listAdCampaigns,
  listAdTemplates,
  proposeAdAction,
  type AdAccount,
  type AdCampaign,
  type AdTemplate,
  type BuildCampaignProposal,
} from "@/lib/api";

import { fromCents } from "./format";

const STATUS_STYLE: Record<AdCampaign["status"], string> = {
  draft: "border-white/10 bg-white/5 text-zinc-400",
  paused: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  active: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  ended: "border-white/10 bg-white/5 text-zinc-500",
  error: "border-red-400/30 bg-red-400/10 text-red-300",
};

// A proposed-but-not-yet-approved build, held in the UI between Build and Approve.
type PendingBuild = BuildCampaignProposal & { templateSlug: string };

export default function Campaigns({ token }: { token: string }) {
  const [accounts, setAccounts] = useState<AdAccount[]>([]);
  const [templates, setTemplates] = useState<AdTemplate[]>([]);
  const [campaigns, setCampaigns] = useState<AdCampaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const [accountId, setAccountId] = useState<string>("");
  const [building, setBuilding] = useState<string | null>(null); // template slug currently building
  const [pending, setPending] = useState<PendingBuild | null>(null);
  const [approving, setApproving] = useState(false);
  const [actingId, setActingId] = useState<string | null>(null); // campaign id under an activate/pause

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [accs, tpls, camps] = await Promise.all([
        listAdAccounts(token),
        listAdTemplates(token),
        listAdCampaigns(token),
      ]);
      setAccounts(accs);
      setTemplates(tpls);
      setCampaigns(camps);
      setAccountId((id) => id || accs[0]?.id || "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load campaigns — try again.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const selectedAccount = accounts.find((a) => a.id === accountId) ?? null;

  // ── Build = PROPOSE only (no platform write). Surfaces the inert proposal for the operator to approve.
  async function build(template: AdTemplate) {
    if (!accountId || building) return;
    setBuilding(template.slug);
    setError(null);
    setNote(null);
    setPending(null);
    try {
      const proposal = await buildCampaign(token, accountId, { templateId: template.id });
      setPending({ ...proposal, templateSlug: template.slug });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't build that campaign — try again.");
    } finally {
      setBuilding(null);
    }
  }

  // ── Approve = APPROVE + EXECUTE the proposed create (campaign is created PAUSED — no spend starts).
  async function approveBuild() {
    if (!pending || approving) return;
    setApproving(true);
    setError(null);
    try {
      await approveAndExecuteAction(token, pending.action_id);
      setNote(`Created "${pending.campaign_name}" — paused. Activate it below when you're ready to spend.`);
      setPending(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't approve that campaign — try again.");
    } finally {
      setApproving(false);
    }
  }

  // ── Activate = a SEPARATE money action (propose→approve→execute the ads.activate_campaign kind).
  async function activate(c: AdCampaign) {
    const ref = c.external_campaign_id;
    if (!ref || actingId) return;
    setActingId(c.id);
    setError(null);
    setNote(null);
    try {
      await proposeAdAction(
        token,
        "ads.activate_campaign",
        { platform: c.platform, campaign_ref: ref },
        "activate this campaign",
      );
      setNote(`Activated "${c.name}" — it's now spending up to its daily cap.`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't activate this campaign — try again.");
    } finally {
      setActingId(null);
    }
  }

  async function pause(c: AdCampaign) {
    const ref = c.external_campaign_id;
    if (!ref || actingId) return;
    setActingId(c.id);
    setError(null);
    setNote(null);
    try {
      await proposeAdAction(
        token,
        "ads.pause_campaign",
        { platform: c.platform, campaign_ref: ref },
        "pause this campaign",
      );
      setNote(`Paused "${c.name}" — spend stopped.`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't pause this campaign — try again.");
    } finally {
      setActingId(null);
    }
  }

  if (loading && campaigns.length === 0 && templates.length === 0) {
    return (
      <div className="panel grid place-items-center px-6 py-16 text-zinc-500">
        <Spinner />
        <span className="mt-3 text-sm">Loading campaigns…</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-200">
          {error}
          <button className="ml-3 underline underline-offset-2" onClick={() => void load()}>Retry</button>
        </div>
      )}
      {note && (
        <div className="rounded-xl border border-accent/30 bg-accent/10 px-4 py-2.5 text-sm text-accent-soft">{note}</div>
      )}

      {/* ── Build from a template ─────────────────────────────────────────────────────────────────── */}
      <Panel
        title="Build a campaign"
        aside={accounts.length ? undefined : "connect an ad account first"}
      >
        <div className="px-5 py-4">
          {accounts.length === 0 ? (
            <p className="text-sm text-zinc-500">
              No ad account is connected yet. Connect Meta or Google Ads on the Accounts tab, then build a campaign here.
            </p>
          ) : (
            <>
              <div className="mb-4 flex flex-wrap items-center gap-3">
                <span className="label">Ad account</span>
                <select
                  value={accountId}
                  onChange={(e) => setAccountId(e.target.value)}
                  className="rounded-xl border border-white/[0.08] bg-ink-900/70 px-3 py-2 text-sm text-zinc-100 outline-none"
                >
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.display_name ?? a.external_account_id} · {a.platform}
                      {a.status !== "connected" ? ` (${a.status})` : ""}
                    </option>
                  ))}
                </select>
              </div>

              {templates.length === 0 ? (
                <p className="text-sm text-zinc-500">No campaign templates are seeded yet.</p>
              ) : (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {templates.map((t) => (
                    <div key={t.id} className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium text-zinc-100">{t.name}</div>
                          <div className="label mt-0.5">{t.template_type.replace(/_/g, " ")} · {t.objective}</div>
                        </div>
                        <button
                          className="btn-primary shrink-0 !px-3 !py-1.5 text-xs"
                          disabled={building !== null || !selectedAccount}
                          onClick={() => void build(t)}
                        >
                          {building === t.slug ? "Building…" : "Build campaign"}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </Panel>

      {/* ── The proposed (inert) build awaiting approval ──────────────────────────────────────────── */}
      {pending && (
        <div className="panel border border-amber-400/30 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="inline-flex rounded-md border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-amber-300">
                  Proposed · {pending.status}
                </span>
                <span className="text-sm font-semibold text-zinc-100">{pending.campaign_name}</span>
              </div>
              <p className="mt-1.5 text-[13px] text-zinc-400">
                {pending.platform} · daily {fromCents(pending.daily_budget_cents)} · lifetime cap{" "}
                {fromCents(pending.lifetime_cap_cents)}. Nothing is live yet — approving creates the campaign{" "}
                <span className="text-zinc-200">paused</span>.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button className="btn-ghost !px-3 !py-1.5 text-xs" disabled={approving} onClick={() => setPending(null)}>
                Discard
              </button>
              <button className="btn-primary !px-3 !py-1.5 text-xs" disabled={approving} onClick={approveBuild}>
                {approving ? "Approving…" : "Approve & create (paused)"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Live + draft campaigns with spend vs cap ──────────────────────────────────────────────── */}
      <Panel title="Campaigns" aside={`${campaigns.length} total`}>
        {campaigns.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">No campaigns yet — build one from a template above.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                <th>Campaign</th>
                <th>Status</th>
                <th className="text-right">Daily cap</th>
                <th className="text-right">Spend</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map((c) => {
                const busy = actingId === c.id;
                const canAct = !!c.external_campaign_id;
                return (
                  <tr key={c.id} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                    <td>
                      <div className="font-medium text-zinc-100">{c.name}</div>
                      <div className="label mt-0.5">{c.platform}</div>
                    </td>
                    <td>
                      <span className={`inline-flex rounded-md border px-2 py-0.5 text-[11px] font-medium capitalize ${STATUS_STYLE[c.status]}`}>
                        {c.status}
                      </span>
                    </td>
                    <td className="num text-right text-zinc-300">{fromCents(c.daily_budget_cents)}</td>
                    <td className="num text-right text-zinc-300">{fromCents(c.spend_cents)}</td>
                    <td className="text-right">
                      {c.status === "active" ? (
                        <button className="btn-ghost !px-3 !py-1.5 text-xs" disabled={busy || !canAct} onClick={() => void pause(c)}>
                          {busy ? "Pausing…" : "Pause"}
                        </button>
                      ) : c.status === "paused" || c.status === "draft" ? (
                        <button
                          className="rounded-lg border border-emerald-400/40 bg-emerald-400/10 px-3 py-1.5 text-xs font-medium text-emerald-300 transition hover:bg-emerald-400/20 disabled:opacity-50"
                          disabled={busy || !canAct}
                          title="Starts spend — an operator + two-step verification is required"
                          onClick={() => void activate(c)}
                        >
                          {busy ? "Activating…" : "Activate 💳"}
                        </button>
                      ) : (
                        <span className="text-[11px] text-zinc-600">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Panel>

      <p className="text-[11px] text-zinc-600">
        <span className="text-amber-300">Activate</span> starts real spend — it is a money action gated to a platform
        operator with two-step verification. Build only proposes; nothing goes live until you approve it, and even
        then the campaign is created paused.
      </p>
    </div>
  );
}
