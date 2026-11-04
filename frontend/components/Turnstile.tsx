"use client";

import { useEffect, useRef } from "react";

// Cloudflare Turnstile widget. Loads the Turnstile script once and renders an explicit widget that
// calls back with a token. Pairs with Supabase Auth's "Enable Captcha protection" (Turnstile provider):
// the token is passed to signInWithPassword / resetPasswordForEmail as options.captchaToken.

const SCRIPT_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js";

type TurnstileApi = {
  render: (el: HTMLElement, opts: Record<string, unknown>) => string;
  reset: (id?: string) => void;
  remove: (id?: string) => void;
};

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

export default function Turnstile({
  siteKey,
  onToken,
  onExpire,
  theme = "dark",
}: {
  siteKey: string;
  onToken: (token: string) => void;
  onExpire?: () => void;
  theme?: "dark" | "light" | "auto";
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);
  const onTokenRef = useRef(onToken);
  const onExpireRef = useRef(onExpire);
  onTokenRef.current = onToken;
  onExpireRef.current = onExpire;

  useEffect(() => {
    let cancelled = false;
    let poll: ReturnType<typeof setInterval> | undefined;

    const render = () => {
      if (cancelled || !containerRef.current || !window.turnstile || widgetId.current) return;
      widgetId.current = window.turnstile.render(containerRef.current, {
        sitekey: siteKey,
        theme,
        callback: (token: string) => onTokenRef.current(token),
        "expired-callback": () => onExpireRef.current?.(),
        "error-callback": () => onExpireRef.current?.(),
      });
    };

    if (window.turnstile) {
      render();
    } else {
      if (!document.querySelector(`script[src="${SCRIPT_SRC}"]`)) {
        const script = document.createElement("script");
        script.src = SCRIPT_SRC;
        script.async = true;
        script.defer = true;
        document.head.appendChild(script);
      }
      poll = setInterval(() => {
        if (window.turnstile) {
          render();
          if (widgetId.current && poll) clearInterval(poll);
        }
      }, 200);
    }

    return () => {
      cancelled = true;
      if (poll) clearInterval(poll);
      if (widgetId.current && window.turnstile) {
        try {
          window.turnstile.remove(widgetId.current);
        } catch {
          /* widget already gone */
        }
        widgetId.current = null;
      }
    };
  }, [siteKey, theme]);

  return <div ref={containerRef} className="mt-3 min-h-[65px]" />;
}

/** Refresh the rendered widget for a new single-use token (call after a failed/used attempt). */
export function resetTurnstile(): void {
  try {
    window.turnstile?.reset();
  } catch {
    /* no widget rendered */
  }
}

/** The configured Turnstile site key (public). Empty string ⇒ captcha is off (no widget, no token). */
export const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? "";
