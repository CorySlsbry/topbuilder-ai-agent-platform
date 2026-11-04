"use client";

import { useEffect, useRef, useState } from "react";

import type { KpiDef } from "@/lib/types";

const storageKey = (deptKey: string) => `tba.scorecard.${deptKey}.visible`;

/** Read the persisted visible-key set for a department. Guards SSR (no window) and any malformed/
 * tampered stored JSON, and intersects with the live catalog so a renamed/removed KPI can't linger.
 * Falls back to `fallback` (the dept's default keys) when absent or unusable. */
export function loadVisibleKeys(deptKey: string, validKeys: string[], fallback: string[]): string[] {
  if (typeof window === "undefined") return fallback;
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(storageKey(deptKey));
  } catch {
    return fallback; // localStorage can throw (privacy mode, quota) — degrade to the default.
  }
  if (raw === null) return fallback;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return fallback;
    const valid = new Set(validKeys);
    const cleaned = parsed.filter((k): k is string => typeof k === "string" && valid.has(k));
    // An empty saved set is legitimate (the user hid everything); only fall back when nothing parsed.
    return parsed.length > 0 && cleaned.length === 0 ? fallback : cleaned;
  } catch {
    return fallback; // not JSON — degrade to the default.
  }
}

function persistVisibleKeys(deptKey: string, keys: string[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(storageKey(deptKey), JSON.stringify(keys));
  } catch {
    /* best-effort — a failed write just means it won't persist this session. */
  }
}

function clearVisibleKeys(deptKey: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(storageKey(deptKey));
  } catch {
    /* best-effort */
  }
}

/** Hook owning the persisted visible-key set for one department. Returns the live set + mutators;
 * every change is written through to localStorage (key `tba.scorecard.<deptKey>.visible`). */
export function useVisibleKpis(deptKey: string, validKeys: string[], defaults: string[]) {
  // SSR-safe: start from `defaults` so server + first client render match (no hydration mismatch),
  // then hydrate from storage in an effect.
  const [visible, setVisible] = useState<string[]>(defaults);

  useEffect(() => {
    setVisible(loadVisibleKeys(deptKey, validKeys, defaults));
    // Re-run only when the department changes; validKeys/defaults are derived from the same dept.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deptKey]);

  const toggle = (key: string) => {
    setVisible((cur) => {
      const next = cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key];
      persistVisibleKeys(deptKey, next);
      return next;
    });
  };

  const reset = () => {
    clearVisibleKeys(deptKey);
    setVisible(defaults);
  };

  // Preserve the catalog's order (not toggle order) so the grid reads predictably.
  const orderedVisible = validKeys.filter((k) => visible.includes(k));
  const isDefault =
    orderedVisible.length === defaults.length && defaults.every((k) => visible.includes(k));

  return { visible: orderedVisible, toggle, reset, isDefault };
}

/** A popover checklist of EVERY catalog KPI for the department (calculated ones badged "calc").
 * Toggling shows/hides that KPI's card. Default-on = the dept's primary keys; the rest are listed
 * to add. A "Reset to default" affordance restores the dept defaults. */
export default function KpiSelector({
  catalog,
  visible,
  onToggle,
  onReset,
  isDefault,
}: {
  catalog: KpiDef[];
  visible: string[];
  onToggle: (key: string) => void;
  onReset: () => void;
  isDefault: boolean;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const visibleSet = new Set(visible);

  // Close on outside-click + Escape.
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (catalog.length === 0) return null;

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="true"
        aria-expanded={open}
        className="btn-ghost px-2.5 py-1 text-xs"
      >
        <GridIcon />
        <span>
          KPIs <span className="num text-zinc-500">({visible.length}/{catalog.length})</span>
        </span>
        <Chevron open={open} />
      </button>

      {open && (
        <div className="absolute right-0 z-30 mt-2 w-72 overflow-hidden rounded-xl border border-white/10 bg-ink-900/95 shadow-panel backdrop-blur-md">
          <div className="flex items-center justify-between border-b border-white/[0.06] px-3 py-2">
            <span className="label">Show / hide KPIs</span>
            <button
              type="button"
              onClick={onReset}
              disabled={isDefault}
              className="text-xs text-accent-soft underline-offset-2 hover:underline disabled:cursor-default disabled:text-zinc-600 disabled:no-underline"
            >
              Reset to default
            </button>
          </div>
          <div className="max-h-72 overflow-y-auto py-1">
            {catalog.map((def) => {
              const checked = visibleSet.has(def.key);
              return (
                <button
                  key={def.key}
                  type="button"
                  onClick={() => onToggle(def.key)}
                  role="menuitemcheckbox"
                  aria-checked={checked}
                  className="flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-sm hover:bg-white/[0.06]"
                >
                  <Checkbox checked={checked} />
                  <span className={`flex-1 truncate ${checked ? "text-zinc-200" : "text-zinc-400"}`}>
                    {def.label}
                  </span>
                  {def.calculated && (
                    <span
                      className="shrink-0 rounded border border-accent/30 bg-accent/10 px-1 py-px text-[9px] font-semibold uppercase tracking-wide text-accent-soft"
                      title="Calculated — derived from raw KPIs (ADR-0003)"
                    >
                      calc
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function Checkbox({ checked }: { checked: boolean }) {
  return (
    <span
      className={`grid h-4 w-4 shrink-0 place-items-center rounded border transition ${
        checked ? "border-accent bg-accent text-white" : "border-white/20 bg-transparent"
      }`}
    >
      {checked && (
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" aria-hidden>
          <path d="M5 12.5l4.2 4.2L19 7" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </span>
  );
}

function GridIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="3" y="3" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.8" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.8" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.8" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="11"
      height="11"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      className={`transition-transform ${open ? "rotate-180" : ""}`}
    >
      <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
