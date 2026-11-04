"use client";

import { useEffect, useRef, useState } from "react";

import { Spinner } from "@/components/ui";
import {
  getGoogleConnectUrl,
  getPolicies,
  getProviders,
  getQuickBooksConnectUrl,
  getTenantProvider,
  getTenantVoice,
  getVoiceOptions,
  setPolicy,
  setTenantProvider,
  setTenantVoice,
  type ProviderInfo,
  type TenantProvider,
  type VoiceOption,
} from "@/lib/api";
import type { AgentMode } from "@/lib/types";

const AGENTS = [
  { key: "booking", label: "Booking (24/7)", desc: "Answers and qualifies inbound; books appointments." },
  { key: "routing", label: "Routing / Dispatch", desc: "Optimizes the day's technician assignments." },
  { key: "communications", label: "Communications", desc: "Triages calls/sms/email; drafts replies." },
  { key: "workforce", label: "Workforce", desc: "Forecasts understaffing + avoidable overtime." },
  { key: "financial", label: "Financial", desc: "Projects cash and flags margin leakage." },
  { key: "inventory", label: "Inventory", desc: "Reorders, shrinkage, unbilled materials." },
  { key: "collections", label: "Collections (A/R)", desc: "Works aged A/R; drafts + sends dunning email/SMS/calls with approval." },
];

const MODES: { mode: AgentMode; label: string; hint: string }[] = [
  { mode: "off", label: "Off", hint: "Advisory only — never writes." },
  { mode: "hitl", label: "Approve", hint: "Proposes; a human approves before it writes." },
  { mode: "auto", label: "Auto", hint: "Acts autonomously, with undo." },
];

function pillClass(active: boolean, mode: AgentMode): string {
  if (!active) return "text-zinc-500 hover:text-zinc-300";
  if (mode === "auto") return "bg-emerald-400/15 text-emerald-300";
  if (mode === "off") return "bg-white/10 text-zinc-300";
  return "bg-accent/15 text-accent";
}

export default function AgentControls({ token }: { token: string }) {
  const [modes, setModes] = useState<Record<string, AgentMode>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<Set<string>>(new Set());
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [tenantProvider, setTenantProviderState] = useState<TenantProvider | null>(null);
  const [providerSaving, setProviderSaving] = useState(false);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [policyError, setPolicyError] = useState<string | null>(null);
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [voice, setVoice] = useState<string | null>(null);
  const [voiceSaving, setVoiceSaving] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const [previewFailed, setPreviewFailed] = useState<Set<string>>(new Set());
  const [googleConnecting, setGoogleConnecting] = useState(false);
  const [googleError, setGoogleError] = useState<string | null>(null);
  const [qboConnecting, setQboConnecting] = useState(false);
  const [qboError, setQboError] = useState<string | null>(null);
  // One shared player — starting a preview stops whichever one was playing.
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const pols = await getPolicies(token);
        const map: Record<string, AgentMode> = {};
        for (const p of pols) map[p.agent] = p.mode;
        setModes(map);
      } catch (e) {
        setPolicyError(e instanceof Error ? e.message : "Couldn't load agent controls — try again.");
      } finally {
        setLoading(false);
      }
    })();
    void (async () => {
      try {
        const [list, current] = await Promise.all([getProviders(token), getTenantProvider(token)]);
        setProviders(list);
        setTenantProviderState(current);
      } catch {
        /* provider layer unavailable → hide the panel */
      }
    })();
    void (async () => {
      try {
        const [opts, current] = await Promise.all([getVoiceOptions(token), getTenantVoice(token)]);
        setVoices(opts);
        setVoice(current.voice);
      } catch {
        /* voice layer unavailable → hide the panel */
      }
    })();
  }, [token]);

  useEffect(() => {
    // Stop any playing preview when the view unmounts.
    return () => audioRef.current?.pause();
  }, []);

  function togglePreview(v: VoiceOption) {
    const audio = audioRef.current ?? (audioRef.current = new Audio());
    if (playing === v.key) {
      audio.pause();
      setPlaying(null);
      return;
    }
    audio.pause();
    const fail = () => {
      // ignore stale events from a src we've already switched away from
      if (!audio.src.endsWith(v.preview_url)) return;
      setPlaying((p) => (p === v.key ? null : p));
      setPreviewFailed((s) => new Set(s).add(v.key));
    };
    audio.onended = () => setPlaying((p) => (p === v.key ? null : p));
    audio.onerror = fail;
    audio.src = v.preview_url;
    setPlaying(v.key);
    setPreviewFailed((s) => {
      if (!s.has(v.key)) return s;
      const next = new Set(s);
      next.delete(v.key); // a retry gets a clean slate
      return next;
    });
    void audio.play().catch((err) => {
      // pause()/src-swap during a pending play() rejects with AbortError — not a real failure
      if ((err as DOMException)?.name !== "AbortError") fail();
    });
  }

  async function chooseVoice(key: string) {
    if (voiceSaving || key === voice) return;
    const previous = voice;
    setVoiceSaving(true);
    setVoiceError(null);
    setVoice(key);
    try {
      const res = await setTenantVoice(token, key);
      setVoice(res.voice);
    } catch (e) {
      setVoice(previous); // the server rejected it — revert the visual selection
      setVoiceError(e instanceof Error ? e.message : "Couldn't change the phone voice — try again.");
    } finally {
      setVoiceSaving(false);
    }
  }

  async function chooseProvider(slug: string) {
    if (!tenantProvider || slug === tenantProvider.provider) return;
    setProviderSaving(true);
    setProviderError(null);
    try {
      setTenantProviderState(await setTenantProvider(token, slug));
    } catch (e) {
      setProviderError(e instanceof Error ? e.message : "Couldn't switch systems — try again.");
    } finally {
      setProviderSaving(false);
    }
  }

  async function connectGoogle() {
    if (googleConnecting) return;
    setGoogleConnecting(true);
    setGoogleError(null);
    try {
      const { authorize_url } = await getGoogleConnectUrl(token);
      window.location.href = authorize_url; // hand off to Google's consent screen
    } catch (e) {
      setGoogleError(e instanceof Error ? e.message : "Couldn't start the Google connection — try again.");
      setGoogleConnecting(false);
    }
  }

  async function connectQuickBooks() {
    if (qboConnecting) return;
    setQboConnecting(true);
    setQboError(null);
    try {
      const { authorize_url } = await getQuickBooksConnectUrl(token);
      window.location.href = authorize_url; // hand off to Intuit's consent screen
    } catch (e) {
      setQboError(e instanceof Error ? e.message : "Couldn't start the QuickBooks connection — try again.");
      setQboConnecting(false);
    }
  }

  async function choose(agent: string, mode: AgentMode) {
    if (saving.has(agent)) return;
    const previous = modes[agent] ?? "hitl";
    setSaving((s) => new Set(s).add(agent));
    setPolicyError(null);
    setModes((m) => ({ ...m, [agent]: mode }));
    try {
      await setPolicy(token, agent, mode);
    } catch (e) {
      setModes((m) => ({ ...m, [agent]: previous })); // the server rejected it — undo the optimistic flip
      setPolicyError(e instanceof Error ? e.message : "Couldn't change that agent's autonomy — try again.");
    } finally {
      setSaving((s) => {
        const next = new Set(s);
        next.delete(agent);
        return next;
      });
    }
  }

  if (loading) {
    return (
      <div className="panel grid place-items-center px-6 py-16 text-zinc-500">
        <Spinner />
        <span className="mt-3 text-sm">Loading agent controls…</span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {tenantProvider && (
        <div className="panel flex flex-wrap items-center justify-between gap-4 p-5">
          <div className="max-w-xl">
            <h2 className="text-sm font-semibold text-zinc-100">Your field system</h2>
            <p className="label mt-1">
              the agents read from and narrate in the language of the system you already run
            </p>
            {(() => {
              const sel = providers.find((p) => p.slug === tenantProvider.provider);
              if (!sel?.connect) return null;
              return (
                <p className="mt-1.5 text-xs text-zinc-500">
                  {sel.status === "live"
                    ? "Fully supported — "
                    : sel.status === "adapter_ready"
                      ? "Connect-ready — "
                      : "Demo data today — "}
                  {sel.connect}
                </p>
              );
            })()}
            {providerError && <p className="mt-1.5 text-xs text-red-400">{providerError}</p>}
          </div>
          <div className="flex items-center gap-3">
            {providerSaving && <Spinner />}
            <select
              value={tenantProvider.provider}
              disabled={providerSaving}
              onChange={(e) => void chooseProvider(e.target.value)}
              className="rounded-xl border border-white/[0.08] bg-ink-900/70 px-3 py-2 text-sm text-zinc-100 outline-none"
            >
              {providers.map((p) => (
                <option key={p.slug} value={p.slug}>
                  {p.display}
                  {p.segment === "construction" ? " (builders)" : ""}
                </option>
              ))}
            </select>
            <span className="inline-flex rounded-md border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[11px] font-medium text-emerald-300">
              {tenantProvider.display}
            </span>
          </div>
        </div>
      )}
      <div className="panel flex flex-wrap items-center justify-between gap-4 p-5">
        <div className="max-w-xl">
          <h2 className="text-sm font-semibold text-zinc-100">Connect Google Drive &amp; Sheets</h2>
          <p className="label mt-1">
            link your Drive so the Financial agent can read your AR-tracker sheet and budget-to-actual doc directly
          </p>
          {googleError && <p className="mt-1.5 text-xs text-red-400">{googleError}</p>}
        </div>
        <button
          type="button"
          onClick={() => void connectGoogle()}
          disabled={googleConnecting}
          className="rounded-xl border border-white/[0.08] bg-ink-900/70 px-4 py-2 text-sm font-medium text-zinc-100 outline-none transition hover:border-accent/40 disabled:opacity-60"
        >
          {googleConnecting ? "Connecting…" : "Connect Google Drive"}
        </button>
      </div>
      <div className="panel flex flex-wrap items-center justify-between gap-4 p-5">
        <div className="max-w-xl">
          <h2 className="text-sm font-semibold text-zinc-100">Connect QuickBooks Online</h2>
          <p className="label mt-1">
            link your QuickBooks company so the Financial agent reads your A/R aging, P&amp;L, and cash
            directly — the Finance scorecard and collections run off your real books, no Zapier
          </p>
          {qboError && <p className="mt-1.5 text-xs text-red-400">{qboError}</p>}
        </div>
        <button
          type="button"
          onClick={() => void connectQuickBooks()}
          disabled={qboConnecting}
          className="rounded-xl border border-white/[0.08] bg-ink-900/70 px-4 py-2 text-sm font-medium text-zinc-100 outline-none transition hover:border-accent/40 disabled:opacity-60"
        >
          {qboConnecting ? "Connecting…" : "Connect QuickBooks"}
        </button>
      </div>
      {voices.length > 0 && (
        <div className="panel p-5">
          <h2 className="text-sm font-semibold text-zinc-100">Phone voice</h2>
          <p className="label mt-1">
            the voice that answers your phones 24/7 — pick the one that fits your brand
          </p>
          {voiceError && <p className="mt-1.5 text-xs text-red-400">{voiceError}</p>}
          <div className="mt-4 flex flex-wrap gap-3">
            {voices.map((v) => {
              const selected = v.key === voice;
              const isPlaying = playing === v.key;
              return (
                <div
                  key={v.key}
                  className={`min-w-[210px] flex-1 rounded-xl border p-4 transition ${
                    selected
                      ? "border-accent/50 bg-accent/[0.06] ring-1 ring-accent/40"
                      : "border-white/[0.08] bg-white/[0.02]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-medium text-zinc-100">{v.label}</div>
                    {selected && (
                      <span className="inline-flex rounded-md border border-accent/30 bg-accent/10 px-2 py-0.5 text-[11px] font-medium text-accent-soft">
                        Answering your phones
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-[13px] text-zinc-500">{v.description}</p>
                  <div className="mt-3 flex items-center gap-2">
                    <button
                      onClick={() => togglePreview(v)}
                      title={isPlaying ? "Stop preview" : "Play preview"}
                      className="rounded-lg border border-white/10 bg-white/[0.02] px-2.5 py-1 text-xs font-medium text-zinc-300 transition hover:bg-white/[0.06]"
                    >
                      {isPlaying ? "⏸ Playing" : "▶ Preview"}
                    </button>
                    {!selected && (
                      <button
                        disabled={voiceSaving}
                        onClick={() => void chooseVoice(v.key)}
                        className="rounded-lg border border-accent/40 bg-accent/10 px-2.5 py-1 text-xs font-medium text-accent-soft transition hover:bg-accent/20 disabled:opacity-50"
                      >
                        Select
                      </button>
                    )}
                    {voiceSaving && selected && <Spinner />}
                    {previewFailed.has(v.key) && (
                      <span className="text-[11px] text-zinc-600">preview unavailable</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
      <div className="panel p-5">
        <h2 className="text-sm font-semibold text-zinc-100">Agent autonomy</h2>
        <p className="label mt-1">
          one switch per agent · default Approve (human-in-the-loop) · every action audited + reversible
        </p>
        {policyError && <p className="mt-1.5 text-xs text-red-400">{policyError}</p>}
      </div>
      {AGENTS.map((a) => {
        const cur = modes[a.key] ?? "hitl";
        return (
          <div key={a.key} className="panel flex flex-wrap items-center justify-between gap-4 p-5">
            <div>
              <div className="text-sm font-medium text-zinc-100">{a.label}</div>
              <div className="text-[13px] text-zinc-500">{a.desc}</div>
            </div>
            <div className="inline-flex rounded-xl border border-white/[0.08] bg-ink-900/70 p-1">
              {MODES.map((m) => (
                <button
                  key={m.mode}
                  title={m.hint}
                  disabled={saving.has(a.key)}
                  onClick={() => choose(a.key, m.mode)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${pillClass(cur === m.mode, m.mode)}`}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
