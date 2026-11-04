"use client";

import { useCallback, useEffect, useState } from "react";

import { Spinner } from "@/components/ui";
import { getAdConnectUrl, listAdAccounts, type AdAccount } from "@/lib/api";

import { timeAgo } from "./format";

type Provider = "meta" | "google_ads";

// A platform's display name + which ad_accounts.platform value its connection produces.
const PROVIDERS: { provider: Provider; label: string; platform: AdAccount["platform"]; blurb: string }[] = [
  {
    provider: "meta",
    label: "Meta",
    platform: "meta",
    blurb: "Facebook & Instagram ad account — geofenced trade-show + lead campaigns.",
  },
  {
    provider: "google_ads",
    label: "Google Ads",
    platform: "google",
    blurb: "Search & Performance Max — intent capture and offline-conversion import.",
  },
];

const STATUS_STYLE: Record<AdAccount["status"], string> = {
  connected: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  disconnected: "border-white/10 bg-white/5 text-zinc-400",
  error: "border-red-400/30 bg-red-400/10 text-red-300",
};

export default function AdAccounts({ token }: { token: string }) {
  const [accounts, setAccounts] = useState<AdAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState<Provider | null>(null);
  const [connectError, setConnectError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setAccounts(await listAdAccounts(token));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load ad accounts — try again.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function connect(provider: Provider) {
    if (connecting) return;
    setConnecting(provider);
    setConnectError(null);
    try {
      const { authorize_url } = await getAdConnectUrl(token, provider);
      window.location.href = authorize_url; // hand off to the platform's consent screen (PKCE + signed state)
    } catch (e) {
      setConnectError(e instanceof Error ? e.message : "Couldn't start the connection — try again.");
      setConnecting(null);
    }
  }

  if (loading && accounts.length === 0) {
    return (
      <div className="panel grid place-items-center px-6 py-16 text-zinc-500">
        <Spinner />
        <span className="mt-3 text-sm">Loading ad accounts…</span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-200">
          {error}
          <button className="ml-3 underline underline-offset-2" onClick={() => void load()}>Retry</button>
        </div>
      )}
      {connectError && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-200">{connectError}</div>
      )}

      {PROVIDERS.map((p) => {
        const account = accounts.find((a) => a.platform === p.platform) ?? null;
        const connected = account?.status === "connected";
        return (
          <div key={p.provider} className="panel flex flex-wrap items-center justify-between gap-4 p-5">
            <div className="max-w-xl">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-zinc-100">{p.label}</h2>
                {account && (
                  <span className={`inline-flex rounded-md border px-2 py-0.5 text-[11px] font-medium capitalize ${STATUS_STYLE[account.status]}`}>
                    {account.status}
                  </span>
                )}
              </div>
              <p className="label mt-1">{p.blurb}</p>
              <p className="mt-1.5 text-xs text-zinc-500">
                {connected
                  ? `Connected${account?.display_name ? ` as ${account.display_name}` : ""}${
                      account?.updated_at ? ` · ${timeAgo(account.updated_at)}` : ""
                    } — tokens held in the encrypted operator vault.`
                  : account?.status === "error"
                    ? "The last connection errored — reconnect to refresh the token."
                    : "Not connected. Connecting links your ad account via OAuth (PKCE + signed state); tokens go to the encrypted operator vault, never the browser."}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void connect(p.provider)}
              disabled={connecting !== null}
              className="rounded-xl border border-white/[0.08] bg-ink-900/70 px-4 py-2 text-sm font-medium text-zinc-100 outline-none transition hover:border-accent/40 disabled:opacity-60"
            >
              {connecting === p.provider
                ? "Connecting…"
                : connected
                  ? `Reconnect ${p.label}`
                  : `Connect ${p.label}`}
            </button>
          </div>
        );
      })}

      <p className="text-[11px] text-zinc-600">
        Connecting an ad platform is a platform-operator action — it requires an operator sign-in with two-step verification.
      </p>
    </div>
  );
}
