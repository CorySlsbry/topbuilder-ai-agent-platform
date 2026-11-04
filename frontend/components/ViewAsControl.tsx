"use client";

import { useEffect, useRef, useState } from "react";

import { Spinner } from "@/components/ui";
import { getAccessMatrix, getOrgOverview } from "@/lib/api";
import type { AccessMatrix, OrgOverview, OrgPerson, SimulatedView } from "@/lib/types";

const FALLBACK_COLOR = "#5b8cff";

function Eye() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12Z" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="12" cy="12" r="2.6" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

export default function ViewAsControl({
  token,
  active,
  onChange,
}: {
  token: string;
  active: SimulatedView | null;
  onChange: (v: SimulatedView | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [overview, setOverview] = useState<OrgOverview | null>(null);
  const [matrix, setMatrix] = useState<AccessMatrix | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [ov, mx] = await Promise.all([getOrgOverview(token), getAccessMatrix(token)]);
      setOverview(ov);
      setMatrix(mx);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the roster");
    } finally {
      setLoading(false);
    }
  }

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && !matrix && !loading) void load();
  }

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function pick(p: OrgPerson) {
    if (!matrix) return;
    const dept = p.department_key;
    // Fail CLOSED: a department missing from the matrix gets no sections/agents; an explicit
    // null (leadership) means all sections — mirror the server's allowed_* null semantics.
    const sections = dept in matrix.dept_sections ? matrix.dept_sections[dept] : [];
    const agents = sections === null ? null : matrix.dept_agents[dept] ?? [];
    onChange({
      personId: p.id,
      name: p.full_name,
      title: p.title,
      department: dept,
      sections,
      agents,
    });
    setOpen(false);
  }

  const deptColor: Record<string, string> = {};
  for (const d of matrix?.departments ?? []) deptColor[d.key] = d.color;
  const groups = (matrix?.departments ?? [])
    .slice()
    .sort((a, b) => a.sort - b.sort)
    .map((d) => ({
      dept: d,
      people: (overview?.people ?? []).filter((p) => p.department_key === d.key),
    }))
    .filter((g) => g.people.length > 0);

  return (
    <div ref={rootRef} className="relative">
      {active ? (
        <span className="inline-flex items-center gap-1.5 rounded-xl border border-accent/40 bg-accent/10 px-3 py-2 text-sm font-medium text-accent-soft">
          <Eye />
          <button className="hover:underline" onClick={toggle} title="Pick someone else">
            {active.name}
          </button>
          <button
            className="ml-0.5 rounded px-1 text-zinc-400 transition hover:text-zinc-100"
            onClick={() => onChange(null)}
            aria-label="Stop viewing as"
            data-testid="viewas-clear"
          >
            ✕
          </button>
        </span>
      ) : (
        <button className="btn-ghost" onClick={toggle} data-testid="viewas-open">
          <Eye />
          View as
        </button>
      )}

      {open && (
        <div className="panel absolute right-0 top-full z-30 mt-2 max-h-96 w-72 overflow-auto p-2">
          {loading ? (
            <div className="grid place-items-center py-8 text-zinc-500">
              <Spinner />
            </div>
          ) : error ? (
            <div className="px-3 py-4 text-sm text-red-300">
              {error}
              <button className="ml-2 underline underline-offset-2" onClick={() => void load()}>Retry</button>
            </div>
          ) : (
            groups.map((g) => (
              <div key={g.dept.key} className="mb-1">
                <div className="label flex items-center gap-1.5 px-2 pb-1 pt-2">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: g.dept.color }} />
                  {g.dept.name}
                </div>
                {g.people.map((p) => (
                  <button
                    key={p.id}
                    className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left transition hover:bg-white/[0.05]"
                    onClick={() => pick(p)}
                    data-testid={`viewas-${p.id}`}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <span
                        className="h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: deptColor[p.department_key] ?? FALLBACK_COLOR }}
                      />
                      <span className="truncate text-[13px] font-medium text-zinc-100">{p.full_name}</span>
                    </span>
                    <span className="shrink-0 text-xs text-zinc-500">{p.title}</span>
                  </button>
                ))}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
