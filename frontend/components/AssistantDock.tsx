"use client";

import { useEffect, useRef, useState } from "react";

import { Spark, Spinner } from "@/components/ui";
import {
  ApiError,
  assistantChat,
  type AssistantAction,
  type AssistantUsage,
  type ChatMsg,
} from "@/lib/api";

// Local message shape: the wire ChatMsg plus the actions the assistant performed for that reply.
type DockMsg = ChatMsg & { actions?: AssistantAction[] };

const QUICK_STARTS = [
  "What needs my attention today?",
  "Draft a follow-up email to a customer",
  "Create a task for the office",
  "Fix my low-performing email workflow",
];

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      title="Copy to clipboard"
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        });
      }}
      className="absolute -right-1 -top-2 rounded-md border border-white/10 bg-ink-900/90 px-1.5 py-0.5 text-[10px] font-medium text-zinc-400 opacity-0 transition hover:text-zinc-200 group-hover:opacity-100"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

export default function AssistantDock({ token, userName }: { token: string; userName?: string | null }) {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<DockMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notConfigured, setNotConfigured] = useState(false);
  const [usage, setUsage] = useState<AssistantUsage | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs, busy, open]);

  async function send(text?: string) {
    const content = (text ?? input).trim().slice(0, 6000);
    if (!content || busy) return;
    const next: DockMsg[] = [...msgs, { role: "user", content }];
    setMsgs(next);
    setInput("");
    setError(null);
    setNotConfigured(false);
    setBusy(true);
    try {
      const wire: ChatMsg[] = next.slice(-12).map((m) => ({ role: m.role, content: m.content }));
      const res = await assistantChat(token, wire);
      setMsgs((m) => [...m, { role: "assistant", content: res.reply, actions: res.actions }]);
      setUsage(res.usage);
    } catch (e) {
      // 404 = the API doesn't have the assistant yet (old deployment) — same UX as unconfigured.
      if (e instanceof ApiError && (e.status === 503 || e.status === 404)) setNotConfigured(true);
      else setError(e instanceof Error ? e.message : "Something went wrong — try again.");
    } finally {
      setBusy(false);
    }
  }

  const rows = Math.min(3, Math.max(1, input.split("\n").length));

  return (
    <>
      {open && (
        <div
          className="panel fixed bottom-20 right-5 z-40 flex max-h-[70vh] w-[min(420px,calc(100vw-2rem))] flex-col"
          data-testid="assistant-panel"
        >
          <div className="flex items-start justify-between gap-3 border-b border-white/[0.06] px-4 py-3">
            <div>
              <h2 className="text-sm font-semibold text-zinc-100">Assistant</h2>
              <p className="label mt-0.5 normal-case tracking-normal">
                drafts emails, answers questions, handles admin tasks — powered by Claude
              </p>
            </div>
            <button
              className="rounded-lg px-1.5 py-0.5 text-zinc-500 transition hover:text-zinc-200"
              onClick={() => setOpen(false)}
              title="Close assistant"
            >
              ✕
            </button>
          </div>

          <div ref={listRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
            {msgs.length === 0 && (
              <div>
                <p className="text-sm text-zinc-400">
                  Hi{userName ? ` ${userName}` : ""} — I can draft emails, dig into your agents&apos;
                  results, and handle admin tasks.
                </p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {QUICK_STARTS.map((q) => (
                    <button
                      key={q}
                      onClick={() => void send(q)}
                      className="rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-xs text-zinc-300 transition hover:border-accent/40 hover:text-accent-soft"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {msgs.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="flex justify-end">
                  <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-accent px-3.5 py-2 text-sm text-white">
                    {m.content}
                  </div>
                </div>
              ) : (
                <div key={i} className="flex flex-col items-start gap-1.5">
                  <div className="group relative max-w-[85%]">
                    <div className="whitespace-pre-wrap rounded-2xl rounded-bl-md border border-white/[0.08] bg-white/[0.05] px-3.5 py-2 text-sm text-zinc-200">
                      {m.content}
                    </div>
                    <CopyButton text={m.content} />
                  </div>
                  {m.actions && m.actions.length > 0 && (
                    <div className="flex max-w-[85%] flex-wrap gap-1.5">
                      {m.actions.map((a, j) => (
                        <span
                          key={j}
                          title={a.tool}
                          className="inline-flex rounded-md border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[11px] font-medium text-emerald-300"
                        >
                          ✓ {a.summary}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ),
            )}
            {busy && (
              <div className="flex items-center gap-2 text-zinc-500">
                <Spinner />
                <span className="text-xs">Thinking…</span>
              </div>
            )}
          </div>

          <div className="border-t border-white/[0.06] px-4 py-3">
            {notConfigured && (
              <p className="mb-2 text-xs text-zinc-500">
                The assistant isn&apos;t configured on this server yet.
              </p>
            )}
            {error && (
              <div className="mb-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs text-red-300">
                {error}
              </div>
            )}
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                rows={rows}
                maxLength={6000}
                placeholder="Ask anything…"
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    void send();
                  }
                }}
                className="field resize-none"
                data-testid="assistant-input"
              />
              <button
                className="btn-primary shrink-0 px-3.5"
                onClick={() => void send()}
                disabled={busy || !input.trim()}
                title="Send"
                data-testid="assistant-send"
              >
                {busy ? <Spinner /> : "Send"}
              </button>
            </div>
            {usage && (
              <div className="label mt-2 text-right">
                {usage.used_today}/{usage.daily_limit} today
              </div>
            )}
          </div>
        </div>
      )}

      <button
        onClick={() => setOpen((v) => !v)}
        title={open ? "Close assistant" : "Open assistant"}
        data-testid="assistant-fab"
        className="fixed bottom-5 right-5 z-40 inline-flex items-center gap-2 rounded-full bg-accent px-4 py-2.5 text-sm font-medium text-white shadow-lg transition hover:bg-accent-soft"
      >
        <Spark />
        Assistant
      </button>
    </>
  );
}
