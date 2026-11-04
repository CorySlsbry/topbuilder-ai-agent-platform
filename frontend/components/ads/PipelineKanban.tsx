"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Spinner } from "@/components/ui";
import { LEAD_STAGES, listLeads, setLeadStage, type CrmLead, type LeadStage } from "@/lib/api";

import LeadDetail from "./LeadDetail";
import { fromCents, timeAgo } from "./format";

const STAGE_LABEL: Record<LeadStage, string> = {
  new: "New",
  contacted: "Contacted",
  booked: "Booked",
  demoed: "Demoed",
  won: "Won",
  lost: "Lost",
};

// Accent ring per column so the board reads at a glance (won = emerald, lost = muted red).
const STAGE_ACCENT: Record<LeadStage, string> = {
  new: "border-sky-400/30",
  contacted: "border-violet-400/30",
  booked: "border-amber-400/30",
  demoed: "border-indigo-400/30",
  won: "border-emerald-400/40",
  lost: "border-red-400/25",
};

function platformOf(lead: CrmLead): string | null {
  return lead.ad_ref?.platform ?? lead.utm?.utm_source ?? null;
}

function LeadCard({
  lead,
  dragging,
  onOpen,
  onDragStart,
  onDragEnd,
}: {
  lead: CrmLead;
  dragging: boolean;
  onOpen: () => void;
  onDragStart: () => void;
  onDragEnd: () => void;
}) {
  const platform = platformOf(lead);
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
      className={`cursor-pointer rounded-xl border border-white/[0.08] bg-white/[0.02] p-3 transition hover:border-accent/40 hover:bg-white/[0.04] ${
        dragging ? "opacity-40" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="truncate text-sm font-medium text-zinc-100">
          {lead.owner ?? lead.source ?? "Lead"}
        </span>
        {lead.value_cents > 0 && (
          <span className="num shrink-0 text-[13px] font-semibold text-emerald-300">{fromCents(lead.value_cents)}</span>
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {platform && (
          <span className="inline-flex rounded-md border border-accent/25 bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-accent-soft">
            {platform}
          </span>
        )}
        <span className="inline-flex rounded-md border border-white/10 bg-white/5 px-1.5 py-0.5 text-[10px] text-zinc-400">
          {lead.source}
        </span>
        <span className="ml-auto text-[10px] text-zinc-600">{timeAgo(lead.created_at)}</span>
      </div>
    </div>
  );
}

export default function PipelineKanban({ token }: { token: string }) {
  const [leads, setLeads] = useState<CrmLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<LeadStage | null>(null);
  const [movingId, setMovingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setLeads(await listLeads(token));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load the pipeline — try again.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const byStage = useMemo(() => {
    const map: Record<LeadStage, CrmLead[]> = {
      new: [], contacted: [], booked: [], demoed: [], won: [], lost: [],
    };
    for (const l of leads) (map[l.stage] ?? map.new).push(l);
    return map;
  }, [leads]);

  const valueByStage = useMemo(() => {
    const map = {} as Record<LeadStage, number>;
    for (const s of LEAD_STAGES) map[s] = byStage[s].reduce((sum, l) => sum + l.value_cents, 0);
    return map;
  }, [byStage]);

  async function move(lead: CrmLead, stage: LeadStage) {
    if (lead.stage === stage || movingId) return;
    const previous = lead.stage;
    // optimistic — flip the card, revert on a server reject (the move is audited server-side).
    setLeads((ls) => ls.map((l) => (l.id === lead.id ? { ...l, stage } : l)));
    setMovingId(lead.id);
    setError(null);
    try {
      const updated = await setLeadStage(token, lead.id, stage);
      setLeads((ls) => ls.map((l) => (l.id === lead.id ? updated : l)));
    } catch (e) {
      setLeads((ls) => ls.map((l) => (l.id === lead.id ? { ...l, stage: previous } : l)));
      setError(e instanceof Error ? e.message : "Couldn't move that lead — try again.");
    } finally {
      setMovingId(null);
    }
  }

  function onDrop(stage: LeadStage) {
    const lead = leads.find((l) => l.id === draggingId);
    setDraggingId(null);
    setDropTarget(null);
    if (lead) void move(lead, stage);
  }

  if (loading && leads.length === 0) {
    return (
      <div className="panel grid place-items-center px-6 py-16 text-zinc-500">
        <Spinner />
        <span className="mt-3 text-sm">Loading the pipeline…</span>
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

      <div className="flex gap-3 overflow-x-auto pb-2">
        {LEAD_STAGES.map((stage) => {
          const cards = byStage[stage];
          const isTarget = dropTarget === stage;
          return (
            <div
              key={stage}
              onDragOver={(e) => {
                e.preventDefault();
                if (dropTarget !== stage) setDropTarget(stage);
              }}
              onDragLeave={(e) => {
                // only clear when actually leaving the column (not crossing a child)
                if (!e.currentTarget.contains(e.relatedTarget as Node)) {
                  setDropTarget((t) => (t === stage ? null : t));
                }
              }}
              onDrop={() => onDrop(stage)}
              className={`flex w-64 shrink-0 flex-col rounded-2xl border bg-ink-900/40 p-2 transition ${
                isTarget ? "border-accent/60 bg-accent/[0.06]" : STAGE_ACCENT[stage]
              }`}
            >
              <div className="flex items-center justify-between px-2 py-1.5">
                <span className="text-xs font-semibold uppercase tracking-wide text-zinc-300">
                  {STAGE_LABEL[stage]}
                </span>
                <span className="num text-[11px] text-zinc-500">{cards.length}</span>
              </div>
              {valueByStage[stage] > 0 && (
                <div className="num px-2 pb-1.5 text-[11px] text-emerald-300/80">{fromCents(valueByStage[stage])}</div>
              )}
              <div className="flex min-h-[80px] flex-1 flex-col gap-2 px-1 pb-1">
                {cards.length === 0 ? (
                  <div className="grid flex-1 place-items-center rounded-xl border border-dashed border-white/[0.06] py-6 text-[11px] text-zinc-600">
                    {isTarget ? "Drop here" : "—"}
                  </div>
                ) : (
                  cards.map((lead) => (
                    <LeadCard
                      key={lead.id}
                      lead={lead}
                      dragging={draggingId === lead.id}
                      onOpen={() => setOpenId(lead.id)}
                      onDragStart={() => setDraggingId(lead.id)}
                      onDragEnd={() => {
                        setDraggingId(null);
                        setDropTarget(null);
                      }}
                    />
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-[11px] text-zinc-600">
        Drag a card to move its stage — every move is recorded as an append-only activity. Click a card to open it.
      </p>

      {openId && (
        <LeadDetail
          token={token}
          leadId={openId}
          onClose={() => setOpenId(null)}
          onChanged={() => void load()}
        />
      )}
    </div>
  );
}
