"use client";

import { useEffect, useRef, useState } from "react";

import type { SupabaseClient } from "@supabase/supabase-js";

import { Spark, Spinner } from "@/components/ui";
import { getAuthConfig, type AuthConfig } from "@/lib/auth-api";
import { getSupabase } from "@/lib/supabase";
import Turnstile, { TURNSTILE_SITE_KEY, resetTurnstile } from "@/components/Turnstile";

type Tenant = { slug: string; name: string };

function friendlyAuthError(message: string): string {
  const m = message.toLowerCase();
  if (m.includes("invalid login credentials")) return "Incorrect email or password.";
  if (m.includes("email not confirmed"))
    return "This email hasn't been confirmed yet. Open the confirmation link you were sent, then sign in again.";
  if (m.includes("rate limit") || m.includes("too many")) return "Too many attempts — wait a minute and try again.";
  return message;
}

export default function AuthGate({
  tenants, error, busy, light, onTheme, onEnter, onAuthed,
}: {
  tenants: Tenant[];
  /** Demo-flow error from the parent (existing dev flow). */
  error: string | null;
  /** Demo-flow busy from the parent (existing dev flow). */
  busy: boolean;
  light: boolean;
  onTheme: () => void;
  /** Existing dev flow — enter a demo tenant. */
  onEnter: (slug: string) => void;
  /** Real login — receives the Supabase access_token. */
  onAuthed: (token: string) => void;
}) {
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [step, setStep] = useState<"password" | "totp" | "reset" | "reset-sent" | "set-password">("password");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [code, setCode] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [authErr, setAuthErr] = useState<string | null>(null);
  const [captchaToken, setCaptchaToken] = useState("");
  const mfaRef = useRef<{ factorId: string; challengeId: string } | null>(null);

  useEffect(() => {
    let alive = true;
    getAuthConfig()
      .then((c) => { if (alive) setConfig(c); })
      .catch(() => {
        // Backend without /auth/config (or unreachable) → fall back to the demo-only experience.
        if (alive) setConfig({ auth_mode: "dev", supabase_url: null, supabase_anon_key: null });
      });
    return () => { alive = false; };
  }, []);

  function client(): SupabaseClient | null {
    if (!config?.supabase_url || !config.supabase_anon_key) return null;
    return getSupabase(config.supabase_url, config.supabase_anon_key);
  }

  // Password-recovery landing: the e-mailed link returns here with a recovery session in the URL
  // hash. Capture the hash BEFORE the client strips it, then also listen for the auth event.
  useEffect(() => {
    if (!config?.supabase_url || !config.supabase_anon_key) return;
    const hadRecoveryHash =
      typeof window !== "undefined" && window.location.hash.includes("type=recovery");
    const sb = getSupabase(config.supabase_url, config.supabase_anon_key);
    if (hadRecoveryHash) setStep("set-password");
    const { data: sub } = sb.auth.onAuthStateChange((event) => {
      if (event === "PASSWORD_RECOVERY") setStep("set-password");
    });
    return () => sub.subscription.unsubscribe();
  }, [config]);

  async function requestReset() {
    const sb = client();
    if (!sb || authBusy) return;
    const addr = email.trim();
    if (!addr) {
      setAuthErr("Enter the e-mail address on your account.");
      return;
    }
    if (TURNSTILE_SITE_KEY && !captchaToken) {
      setAuthErr("Please complete the captcha.");
      return;
    }
    setAuthBusy(true);
    setAuthErr(null);
    try {
      const { error: resetErr } = await sb.auth.resetPasswordForEmail(addr, {
        redirectTo: window.location.origin,
        ...(TURNSTILE_SITE_KEY ? { captchaToken } : {}),
      });
      if (resetErr) {
        setAuthErr(friendlyAuthError(resetErr.message));
        return;
      }
      setStep("reset-sent");
    } catch (e) {
      setAuthErr(e instanceof Error ? e.message : "Could not send the reset e-mail");
    } finally {
      setAuthBusy(false);
      if (TURNSTILE_SITE_KEY) {
        setCaptchaToken("");
        resetTurnstile();
      }
    }
  }

  async function applyNewPassword() {
    const sb = client();
    if (!sb || authBusy) return;
    if (newPassword.length < 10) {
      setAuthErr("Use at least 10 characters.");
      return;
    }
    setAuthBusy(true);
    setAuthErr(null);
    try {
      const { error: updErr } = await sb.auth.updateUser({ password: newPassword });
      if (updErr) {
        setAuthErr(
          /expired|invalid/i.test(updErr.message)
            ? "This reset link has expired — request a new one from the sign-in screen."
            : updErr.message,
        );
        return;
      }
      await finish(sb); // recovery session is live — straight into the command center
    } catch (e) {
      setAuthErr(e instanceof Error ? e.message : "Could not set the new password");
    } finally {
      setAuthBusy(false);
    }
  }

  async function finish(sb: SupabaseClient) {
    const { data, error: sessErr } = await sb.auth.getSession();
    if (sessErr || !data.session) {
      setAuthErr("Signed in, but no session was returned. Try again.");
      return;
    }
    onAuthed(data.session.access_token);
  }

  async function signIn() {
    const sb = client();
    if (!sb || authBusy) return;
    if (!email.trim() || !password) {
      setAuthErr("Enter your email and password.");
      return;
    }
    if (TURNSTILE_SITE_KEY && !captchaToken) {
      setAuthErr("Please complete the captcha.");
      return;
    }
    setAuthBusy(true);
    setAuthErr(null);
    try {
      const { error: signErr } = await sb.auth.signInWithPassword({
        email: email.trim(),
        password,
        ...(TURNSTILE_SITE_KEY ? { options: { captchaToken } } : {}),
      });
      if (signErr) {
        setAuthErr(friendlyAuthError(signErr.message));
        return;
      }
      const { data: aal, error: aalErr } = await sb.auth.mfa.getAuthenticatorAssuranceLevel();
      if (aalErr) {
        setAuthErr(aalErr.message);
        return;
      }
      if (aal.nextLevel === "aal2" && aal.nextLevel !== aal.currentLevel) {
        const { data: factors, error: facErr } = await sb.auth.mfa.listFactors();
        if (facErr) {
          setAuthErr(facErr.message);
          return;
        }
        const totp =
          factors.totp[0] ??
          factors.all.find((f) => f.factor_type === "totp" && f.status === "verified");
        if (!totp) {
          setAuthErr("Two-factor is required but no authenticator is enrolled on this account. Contact your operator.");
          return;
        }
        const { data: challenge, error: chErr } = await sb.auth.mfa.challenge({ factorId: totp.id });
        if (chErr) {
          setAuthErr(chErr.message);
          return;
        }
        mfaRef.current = { factorId: totp.id, challengeId: challenge.id };
        setCode("");
        setStep("totp");
        return;
      }
      await finish(sb);
    } catch (e) {
      setAuthErr(e instanceof Error ? e.message : "Sign-in failed");
    } finally {
      setAuthBusy(false);
      if (TURNSTILE_SITE_KEY) {
        setCaptchaToken("");
        resetTurnstile();
      }
    }
  }

  async function verifyCode() {
    const sb = client();
    if (!sb || !mfaRef.current || authBusy) return;
    const c = code.trim();
    if (!/^\d{6}$/.test(c)) {
      setAuthErr("Enter the 6-digit code from your authenticator app.");
      return;
    }
    setAuthBusy(true);
    setAuthErr(null);
    try {
      const { error: verErr } = await sb.auth.mfa.verify({
        factorId: mfaRef.current.factorId,
        challengeId: mfaRef.current.challengeId,
        code: c,
      });
      if (verErr) {
        setAuthErr(
          /invalid|expired/i.test(verErr.message)
            ? "That code didn't work — check your authenticator app and try again."
            : verErr.message,
        );
        // The challenge may have expired — mint a fresh one for the next attempt.
        const { data: challenge } = await sb.auth.mfa.challenge({ factorId: mfaRef.current.factorId });
        if (challenge) mfaRef.current = { ...mfaRef.current, challengeId: challenge.id };
        setCode("");
        return;
      }
      await finish(sb);
    } catch (e) {
      setAuthErr(e instanceof Error ? e.message : "Verification failed");
    } finally {
      setAuthBusy(false);
    }
  }

  function backToSignIn() {
    mfaRef.current = null;
    setStep("password");
    setCode("");
    setPassword("");
    setAuthErr(null);
    // Abandon the half-finished (aal1) session.
    void client()?.auth.signOut();
  }

  if (!config) {
    return (
      <main className="grid min-h-screen place-items-center px-5 text-zinc-500">
        <Spinner />
      </main>
    );
  }

  const realAvailable = Boolean(config.supabase_url && config.supabase_anon_key);
  const demoAvailable = config.auth_mode === "dev";

  return (
    <main className="grid min-h-screen place-items-center px-5">
      <div className="panel w-full max-w-md p-8">
        <div className="flex items-center justify-between">
          <div className="grid h-11 w-11 place-items-center rounded-xl bg-accent/15 text-accent ring-1 ring-accent/30">
            <Spark />
          </div>
          <button className="btn-ghost" onClick={onTheme}>{light ? "◐ Easy mode" : "◑ Command"}</button>
        </div>
        <h1 className="mt-5 text-xl font-semibold tracking-tight text-zinc-100">Top Builder AI</h1>
        <p className="mt-1 text-sm text-zinc-500">
          {realAvailable
            ? "The AI operating layer for ServiceTitan contractors. Sign in to your command center."
            : "The AI operating layer for ServiceTitan contractors. Choose a demo tenant to enter the command center."}
        </p>

        {realAvailable && step === "password" && (
          <form
            className="mt-6 space-y-3"
            onSubmit={(e) => { e.preventDefault(); void signIn(); }}
          >
            <div>
              <label className="label mb-1.5 block" htmlFor="auth-email">Email</label>
              <input
                id="auth-email"
                data-testid="auth-email"
                type="email"
                autoComplete="email"
                className="field"
                placeholder="person1@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={authBusy}
              />
            </div>
            <div>
              <label className="label mb-1.5 block" htmlFor="auth-password">Password</label>
              <input
                id="auth-password"
                data-testid="auth-password"
                type="password"
                autoComplete="current-password"
                className="field"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={authBusy}
              />
            </div>
            {TURNSTILE_SITE_KEY && (
              <Turnstile siteKey={TURNSTILE_SITE_KEY} onToken={setCaptchaToken} onExpire={() => setCaptchaToken("")} />
            )}
            <button
              type="submit"
              className="btn-primary w-full"
              disabled={authBusy || (!!TURNSTILE_SITE_KEY && !captchaToken)}
              data-testid="auth-submit"
            >
              {authBusy && <Spinner />}
              {authBusy ? "Signing in…" : "Sign in"}
            </button>
            <button
              type="button"
              data-testid="auth-forgot"
              className="w-full text-center text-xs text-zinc-500 transition hover:text-zinc-300"
              onClick={() => { setAuthErr(null); setStep("reset"); }}
              disabled={authBusy}
            >
              Forgot password?
            </button>
          </form>
        )}

        {realAvailable && step === "reset" && (
          <form className="mt-6 space-y-3" onSubmit={(e) => { e.preventDefault(); void requestReset(); }}>
            <div className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3 text-sm text-zinc-400">
              Enter your account e-mail and we'll send a secure link to set a new password.
            </div>
            <div>
              <label className="label mb-1.5 block" htmlFor="reset-email">Email</label>
              <input
                id="reset-email"
                data-testid="reset-email"
                type="email"
                autoComplete="email"
                className="field"
                placeholder="person1@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={authBusy}
                autoFocus
              />
            </div>
            {TURNSTILE_SITE_KEY && (
              <Turnstile siteKey={TURNSTILE_SITE_KEY} onToken={setCaptchaToken} onExpire={() => setCaptchaToken("")} />
            )}
            <button
              type="submit"
              className="btn-primary w-full"
              disabled={authBusy || (!!TURNSTILE_SITE_KEY && !captchaToken)}
              data-testid="reset-submit"
            >
              {authBusy && <Spinner />}
              {authBusy ? "Sending…" : "Send reset link"}
            </button>
            <button
              type="button"
              className="w-full text-center text-xs text-zinc-500 transition hover:text-zinc-300"
              onClick={() => { setAuthErr(null); setStep("password"); }}
              disabled={authBusy}
            >
              ← Back to sign in
            </button>
          </form>
        )}

        {realAvailable && step === "reset-sent" && (
          <div className="mt-6 space-y-3">
            <div className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-200">
              If an account exists for <span className="font-medium">{email.trim()}</span>, a password-reset
              link is on its way. Open it on this device — it brings you straight back here to set the new password.
            </div>
            <button
              type="button"
              className="w-full text-center text-xs text-zinc-500 transition hover:text-zinc-300"
              onClick={() => setStep("password")}
            >
              ← Back to sign in
            </button>
          </div>
        )}

        {realAvailable && step === "set-password" && (
          <form className="mt-6 space-y-3" onSubmit={(e) => { e.preventDefault(); void applyNewPassword(); }}>
            <div className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3 text-sm text-zinc-400">
              You followed a valid reset link — set your new password.
            </div>
            <div>
              <label className="label mb-1.5 block" htmlFor="new-password">New password</label>
              <input
                id="new-password"
                data-testid="new-password"
                type="password"
                autoComplete="new-password"
                className="field"
                placeholder="at least 10 characters"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                disabled={authBusy}
                autoFocus
              />
            </div>
            <button type="submit" className="btn-primary w-full" disabled={authBusy || newPassword.length < 10}>
              {authBusy && <Spinner />}
              {authBusy ? "Saving…" : "Set password & sign in"}
            </button>
          </form>
        )}

        {realAvailable && step === "totp" && (
          <form
            className="mt-6 space-y-3"
            onSubmit={(e) => { e.preventDefault(); void verifyCode(); }}
          >
            <div className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3 text-sm text-zinc-400">
              Two-factor authentication is on for <span className="font-medium text-zinc-200">{email.trim()}</span>.
              Enter the 6-digit code from your authenticator app.
            </div>
            <input
              data-testid="auth-totp"
              className="field num text-center text-lg tracking-[0.4em]"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              placeholder="000000"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              disabled={authBusy}
              autoFocus
            />
            <button type="submit" className="btn-primary w-full" disabled={authBusy || code.length !== 6}>
              {authBusy && <Spinner />}
              {authBusy ? "Verifying…" : "Verify"}
            </button>
            <button
              type="button"
              className="w-full text-center text-xs text-zinc-500 transition hover:text-zinc-300"
              onClick={backToSignIn}
              disabled={authBusy}
            >
              ← Back to sign in
            </button>
          </form>
        )}

        {authErr && <p className="mt-4 text-sm text-red-300">{authErr}</p>}

        {demoAvailable && step === "password" && (
          <>
            {realAvailable ? (
              <div className="mt-7 flex items-center gap-3">
                <div className="h-px flex-1 bg-white/10" />
                <span className="label">View the live demo</span>
                <div className="h-px flex-1 bg-white/10" />
              </div>
            ) : (
              <div className="label mt-6">Live demo</div>
            )}
            <div className="mt-3 space-y-2">
              {tenants.map((t) => (
                <button
                  key={t.slug}
                  data-testid={`tenant-${t.slug}`}
                  onClick={() => onEnter(t.slug)}
                  disabled={busy}
                  className="group flex w-full items-center justify-between rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3 text-left transition hover:border-accent/40 hover:bg-white/[0.05] disabled:opacity-50"
                >
                  <span>
                    <span className="block text-sm font-medium text-zinc-100">{t.name}</span>
                    <span className="num text-xs text-zinc-500">tenant: {t.slug}</span>
                  </span>
                  <span className="text-zinc-600 transition group-hover:translate-x-0.5 group-hover:text-accent">→</span>
                </button>
              ))}
            </div>
            {error && <p className="mt-4 text-sm text-red-300">{error}</p>}
          </>
        )}

        {!realAvailable && !demoAvailable && (
          <div className="mt-6 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
            Sign-in isn't configured for this environment yet. Contact your operator.
          </div>
        )}

        <p className="mt-6 text-[11px] leading-relaxed text-zinc-600">
          Each tenant is isolated by Postgres Row-Level Security. Every agent action is signed, logged, and reversible.
        </p>
      </div>
    </main>
  );
}
