"use client";

import { useState } from "react";

import AdAccounts from "./AdAccounts";
import Campaigns from "./Campaigns";
import PipelineKanban from "./PipelineKanban";

type Tab = "pipeline" | "campaigns" | "accounts";

const TABS: { key: Tab; label: string; blurb: string }[] = [
  { key: "pipeline", label: "Pipeline", blurb: "Your go-to-market leads by stage — drag to move, click to open." },
  { key: "campaigns", label: "Campaigns", blurb: "Build, approve, and activate Meta & Google Ads campaigns through the action gate." },
  { key: "accounts", label: "Accounts", blurb: "Connect Meta & Google Ads — tokens go to the encrypted operator vault." },
];

/** The operator-only Ads & CRM surface (ADR 0009). Every panel here calls a route gated server-side to a
 * platform operator (admin + 2FA + allowlist), so a non-operator that somehow reaches it sees only
 * friendly 403s — never raw data. */
export default function AdsCrmView({ token }: { token: string }) {
  const [tab, setTab] = useState<Tab>("pipeline");
  const active = TABS.find((t) => t.key === tab)!;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-1 rounded-xl border border-white/[0.06] bg-ink-900/40 p-1">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            data-testid={`ads-tab-${t.key}`}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              t.key === tab ? "bg-accent/15 text-accent" : "text-zinc-400 hover:bg-white/[0.04] hover:text-zinc-200"
            }`}
          >
            {t.label}
          </button>
        ))}
        <span className="ml-2 hidden text-xs text-zinc-600 sm:inline">{active.blurb}</span>
      </div>

      {tab === "pipeline" ? (
        <PipelineKanban token={token} />
      ) : tab === "campaigns" ? (
        <Campaigns token={token} />
      ) : (
        <AdAccounts token={token} />
      )}
    </div>
  );
}
