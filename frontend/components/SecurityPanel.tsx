"use client";

import { useCallback, useEffect, useState } from "react";

import type { SupabaseClient } from "@supabase/supabase-js";

import { Spinner } from "@/components/ui";
import type { Me } from "@/lib/auth-api";

// Inline structural type — supabase-js factors are assignable to this.
type TotpFactor = {
  id: string;
  factor_type: string;
  status: string;
  friendly_name?: string;
  created_at: string;
};

type EnrollState = { factorId: string; qrCode: string; secret: string };

export default function SecurityPanel({
  supabase, me, onClose, onAalChanged, onToken,
}: {
  supabase: SupabaseClient;
  me: Me;
  onClose: () => void;
  /** Tell the app to refetch /auth/me (AAL may have changed). */
  onAalChanged: () => void;
  /** The refreshed access_token after enroll/unenroll (the old one keeps the old AAL). */
  onToken: (token: string) => void;
}) {
  const [factors, setFactors] = useState<TotpFactor[] | null>(null); // null = loading
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [enroll, setEnroll] = useState<EnrollState | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const loadFactors = useCallback(async () => {
    setLoadErr(null);
    try {
      const { data, error } = await supabase.auth.mfa.listFactors();
      if (error) throw new Error(error.message);
      setFactors(data.all.filter((f) => f.factor_type === "totp"));
    } catch (e) {
      setFactors([]);
      setLoadErr(e instanceof Error ? e.message : "Could not load your authenticators");
    }
  }, [supabase]);

  useEffect(() => { void loadFactors(); }, [loadFactors]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  /** Refresh the session so the token reflects the new AAL, and hand it up. */
  async function pushRefreshedToken() {
    const { data } = await supabase.auth.refreshSession();
    const token = data.session?.access_token;
    if (token) onToken(token);
    onAalChanged();
  }

  async function startEnroll() {
    setBusy(true);
    setErr(null);
    setDone(null);
    try {
      // Clean up abandoned (unverified) enrollments first — Supabase keeps them around.
      const { data: existing } = await supabase.auth.mfa.listFactors();
      for (const f of existing?.all ?? []) {
        if (f.factor_type === "totp" && f.status !== "verified") {
          await supabase.auth.mfa.unenroll({ factorId: f.id });
        }
      }
      // Branded enrollment: the authenticator app lists this entry as "Top Builder AI", not the raw
      // Supabase project domain.
      const { data, error } = await supabase.auth.mfa.enroll({
        factorType: "totp",
        issuer: "Top Builder AI",
        friendlyName: "Top Builder AI",
      });
      if (error) throw new Error(error.message);
      setEnroll({ factorId: data.id, qrCode: data.totp.qr_code, secret: data.totp.secret });
      setCode("");
      setCopied(false);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not start 2FA setup");
    } finally {
      setBusy(false);
    }
  }

  async function verifyEnroll() {
    if (!enroll || busy) return;
    const c = code.trim();
    if (!/^\d{6}$/.test(c)) {
      setErr("Enter the 6-digit code from your authenticator app.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const { data: challenge, error: chErr } = await supabase.auth.mfa.challenge({ factorId: enroll.factorId });
      if (chErr) throw new Error(chErr.message);
      const { error: verErr } = await supabase.auth.mfa.verify({
        factorId: enroll.factorId,
        challengeId: challenge.id,
        code: c,
      });
      if (verErr) {
        setErr(
          /invalid|expired/i.test(verErr.message)
            ? "That code didn't work — enter the current code from your app."
            : verErr.message,
        );
        return;
      }
      setEnroll(null);
      setCode("");
      setDone("Two-factor authentication is now active on your account.");
      await loadFactors();
      await pushRefreshedToken();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Verification failed");
    } finally {
      setBusy(false);
    }
  }

  async function removeFactor(factorId: string) {
    setBusy(true);
    setErr(null);
    setDone(null);
    try {
      const { error } = await supabase.auth.mfa.unenroll({ factorId });
      if (error) throw new Error(error.message);
      setConfirmId(null);
      setDone("Authenticator removed.");
      await loadFactors();
      await pushRefreshedToken();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not remove the authenticator");
    } finally {
      setBusy(false);
    }
  }

  function copySecret() {
    if (!enroll) return;
    try {
      void navigator.clipboard?.writeText(enroll.secret);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable — the secret is selectable text */
    }
  }

  const verified = factors?.filter((f) => f.status === "verified") ?? [];

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Security settings"
      onClick={onClose}
    >
      <div className="panel w-full max-w-lg p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-zinc-100">Security</h2>
            <p className="mt-0.5 text-sm text-zinc-500">Two-factor authentication for your account.</p>
          </div>
          <button className="btn-ghost" onClick={onClose}>Close</button>
        </div>

        <div className="mt-5 rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-sm font-medium text-zinc-100">{me.email}</div>
              <div className="label mt-0.5">{me.role}</div>
            </div>
            {me.aal === "aal2" ? (
              <span className="inline-flex rounded-md border border-emerald-300/20 bg-emerald-300/10 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-emerald-300">
                2FA active
              </span>
            ) : (
              <span className="inline-flex rounded-md border border-amber-300/20 bg-amber-300/10 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-amber-300">
                2FA not set up
              </span>
            )}
          </div>
        </div>

        {err && <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-200">{err}</div>}
        {done && <div className="mt-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-2.5 text-sm text-emerald-200">{done}</div>}

        <div className="mt-5">
          <div className="label mb-2">Authenticator apps</div>
          {factors === null ? (
            <div className="grid place-items-center rounded-xl border border-white/10 py-8 text-zinc-500">
              <Spinner />
            </div>
          ) : factors.length === 0 ? (
            <p className="text-sm text-zinc-500">
              No authenticator app is enrolled yet. Set one up to protect operator actions.
            </p>
          ) : (
            <ul className="space-y-2">
              {factors.map((f) => (
                <li key={f.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/10 bg-white/[0.02] px-4 py-2.5">
                  <div>
                    <div className="text-sm text-zinc-100">{f.friendly_name || "Authenticator app"}</div>
                    <div className="num text-xs text-zinc-500">
                      {f.status === "verified" ? "verified" : "setup not finished"} · added {f.created_at.slice(0, 10)}
                    </div>
                  </div>
                  {confirmId === f.id ? (
                    <div className="flex items-center gap-2">
                      <button
                        className="rounded-md border border-red-500/40 bg-red-500/10 px-2.5 py-1 text-xs text-red-300 hover:bg-red-500/20 disabled:opacity-50"
                        onClick={() => void removeFactor(f.id)}
                        disabled={busy}
                      >
                        {busy ? "Removing…" : "Confirm remove"}
                      </button>
                      <button
                        className="rounded-md border border-white/10 px-2.5 py-1 text-xs text-zinc-300 hover:bg-white/[0.06]"
                        onClick={() => setConfirmId(null)}
                        disabled={busy}
                      >
                        Keep
                      </button>
                    </div>
                  ) : (
                    <button
                      className="rounded-md border border-white/10 px-2.5 py-1 text-xs text-zinc-400 hover:bg-white/[0.06] hover:text-red-300 disabled:opacity-50"
                      onClick={() => setConfirmId(f.id)}
                      disabled={busy}
                    >
                      Remove
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
          {loadErr && <p className="mt-2 text-xs text-red-300">{loadErr}</p>}
        </div>

        {enroll ? (
          <div className="mt-5 space-y-3">
            <p className="text-sm text-zinc-400">
              Scan this QR code with your authenticator app (1Password, Google Authenticator, Authy…),
              then enter the 6-digit code it shows.
            </p>
            {enroll.qrCode.trimStart().startsWith("<") ? (
              <div
                className="mx-auto w-44 rounded-xl bg-white p-3 [&_svg]:h-auto [&_svg]:w-full"
                dangerouslySetInnerHTML={{ __html: enroll.qrCode }}
              />
            ) : (
              // Some gotrue versions return a data-URI instead of raw SVG.
              // eslint-disable-next-line @next/next/no-img-element
              <img src={enroll.qrCode} alt="2FA QR code" className="mx-auto w-44 rounded-xl bg-white p-3" />
            )}
            <div className="flex items-center justify-between gap-2 rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2">
              <code className="num break-all text-xs text-zinc-300">{enroll.secret}</code>
              <button
                type="button"
                className="shrink-0 rounded-md border border-white/10 px-2.5 py-1 text-xs text-zinc-300 hover:bg-white/[0.06]"
                onClick={copySecret}
              >
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <form
              className="flex gap-2"
              onSubmit={(e) => { e.preventDefault(); void verifyEnroll(); }}
            >
              <input
                data-testid="enroll-totp"
                className="field num flex-1 text-center tracking-[0.4em]"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                placeholder="000000"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                disabled={busy}
                autoFocus
              />
              <button type="submit" className="btn-primary shrink-0" disabled={busy || code.length !== 6}>
                {busy && <Spinner />}
                {busy ? "Verifying…" : "Verify & activate"}
              </button>
            </form>
            <button
              type="button"
              className="w-full text-center text-xs text-zinc-500 transition hover:text-zinc-300"
              onClick={() => { setEnroll(null); setCode(""); setErr(null); }}
              disabled={busy}
            >
              Cancel setup
            </button>
          </div>
        ) : (
          <button
            className="btn-primary mt-5 w-full"
            onClick={() => void startEnroll()}
            disabled={busy || factors === null}
            data-testid="enroll-start"
          >
            {busy && <Spinner />}
            {verified.length > 0 ? "Add another authenticator" : "Set up 2FA"}
          </button>
        )}

        <p className="mt-5 text-[11px] leading-relaxed text-zinc-600">
          Operator actions (approvals, learning rollouts) require a 2FA-verified session.
        </p>
      </div>
    </div>
  );
}
