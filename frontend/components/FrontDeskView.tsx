"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge, Panel, Spinner, usd } from "@/components/ui";
import { approveAndBook, getAgentLatest, listComms, listTasks, runAgent, updateTask } from "@/lib/api";
import type { BookingRunResult, Communication, ProposedBooking, Task } from "@/lib/types";

const CHANNEL_ICON: Record<string, string> = { call: "📞", sms: "💬", email: "✉️", voicemail: "🎙️", web: "🌐" };

export default function FrontDeskView({ token }: { token: string }) {
  const [comms, setComms] = useState<Communication[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [booking, setBooking] = useState<BookingRunResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [c, t, b] = await Promise.all([
        listComms(token),
        listTasks(token),
        getAgentLatest<BookingRunResult>(token, "booking").catch(() => null),
      ]);
      setComms(c);
      setTasks(t);
      setBooking(b);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load the front desk — try again.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function runBooking() {
    setLoading(true);
    setError(null);
    try {
      setBooking(await runAgent<BookingRunResult>(token, "booking"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't run the booking agent — try again.");
    } finally {
      setLoading(false);
    }
  }

  async function approve(bk: ProposedBooking) {
    setBusyId(bk.intake_id);
    setNote(null);
    setError(null);
    try {
      const r = await approveAndBook(token, booking?.run_id ?? null, {
        intake_id: bk.intake_id, trade: bk.trade, proposed_date: bk.proposed_date, caller_name: bk.caller_name,
      });
      const ref = (r.result as { external_ref?: string } | undefined)?.external_ref;
      setNote(`Booked ${bk.caller_name ?? "this caller"} — confirmed${ref ? ` (ref ${ref})` : ""}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't book this appointment — try again.");
    } finally {
      setBusyId(null);
    }
  }

  async function complete(id: string) {
    setTasks((ts) => ts.map((t) => (t.id === id ? { ...t, status: "done" } : t)));
    try {
      await updateTask(token, id, "done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't update that task — try again.");
      void load(); // put the checkbox back the way the server has it
    }
  }

  if (loading && comms.length === 0) {
    return (
      <div className="panel grid place-items-center px-6 py-16 text-zinc-500">
        <Spinner />
        <span className="mt-3 text-sm">Loading front desk…</span>
      </div>
    );
  }

  const proposed = booking?.proposed_bookings ?? [];
  const openTasks = tasks.filter((t) => t.status !== "done").length;

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-200">
          {error}
          <button className="ml-3 underline underline-offset-2" onClick={() => void load()}>Retry</button>
        </div>
      )}
      {note && <div className="rounded-xl border border-accent/30 bg-accent/10 px-4 py-2.5 text-sm text-accent-soft">{note}</div>}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Panel title="Communications" aside={`${comms.length} · all channels`}>
          <ul className="max-h-[440px] divide-y divide-white/[0.04] overflow-auto">
            {comms.map((c) => (
              <li key={c.id} className="flex items-start gap-3 px-5 py-3">
                <span className="mt-0.5 text-base">{CHANNEL_ICON[c.channel] ?? "•"}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium text-zinc-100">{c.contact_name ?? "Unknown caller"}</span>
                    <span className="label shrink-0">{c.channel}{c.agent_handled ? " · handled" : ""}</span>
                  </div>
                  <div className="truncate text-[13px] text-zinc-400">{c.subject}</div>
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Tasks" aside={`${openTasks} open`}>
          <ul className="max-h-[440px] divide-y divide-white/[0.04] overflow-auto">
            {tasks.map((t) => (
              <li key={t.id} className="flex items-start gap-3 px-5 py-3">
                <button
                  onClick={() => complete(t.id)}
                  disabled={t.status === "done"}
                  aria-label="complete task"
                  className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded border text-[10px] ${
                    t.status === "done" ? "border-emerald-400 bg-emerald-400/20 text-emerald-300" : "border-zinc-600 text-transparent hover:border-accent"
                  }`}
                >
                  ✓
                </button>
                <div className="min-w-0 flex-1">
                  <div className={`text-sm ${t.status === "done" ? "text-zinc-500 line-through" : "text-zinc-100"}`}>{t.title}</div>
                  <div className="mt-1 flex items-center gap-2 text-[11px] text-zinc-500">
                    <Badge label={t.department.replace("_", " ")} />
                    {t.source_agent && <span>via {t.source_agent}</span>}
                    {t.priority >= 8 && <span className="font-medium text-red-300">urgent</span>}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <Panel title="Booking queue — proposed (awaiting confirm)" aside={booking ? `${proposed.length} proposed` : "no run yet"}>
        {!booking ? (
          <div className="px-5 py-6">
            <button className="btn-primary" onClick={runBooking}>Run booking agent</button>
          </div>
        ) : proposed.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">No proposed bookings in the latest batch.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                <th>Caller</th><th>Trade</th><th>When</th><th className="text-right">Value</th><th></th>
              </tr>
            </thead>
            <tbody>
              {proposed.map((b) => (
                <tr key={b.intake_id} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                  <td className="font-medium text-zinc-100">
                    {b.caller_name ?? "Unknown"}
                    {b.after_hours && <span className="ml-2 rounded border border-accent/25 bg-accent/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-accent-soft">after hrs</span>}
                  </td>
                  <td><Badge label={b.trade} /></td>
                  <td className="num text-zinc-300">{b.proposed_date}</td>
                  <td className="num text-right text-emerald-300">{usd(b.estimated_value_usd)}</td>
                  <td className="text-right">
                    <button className="btn-primary !px-3 !py-1 text-xs" disabled={busyId === b.intake_id} onClick={() => approve(b)}>
                      {busyId === b.intake_id ? "Booking…" : "Approve & book"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
