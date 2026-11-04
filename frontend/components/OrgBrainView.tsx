"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import OrgSphereLazy from "@/components/OrgSphereLazy";
import { EmptyState, Spinner } from "@/components/ui";
import { getOrgOverview, getOrgPerson, setPersonAgent } from "@/lib/api";
import { computeFocus } from "@/lib/orgFocus";
import { computeDeptAccess } from "@/lib/orgAccess";
import type { AgentOverrideMode, AgentState, OrgAgentCard, OrgDepartment, OrgOverview, OrgPerson, OrgPersonProfile } from "@/lib/types";
import { detectWebGL, prefersReducedMotion } from "@/lib/webgl";

type OrgView = "2d" | "3d";

// ---- deterministic radial layout (precomputed — no force simulation, identical every render) ----
const CX = 520;
const CY = 380;
const TAU = Math.PI * 2;
const SECTOR_GAP = 0.05; // radians between department sectors
const START_ANGLE = -TAU / 4; // first sector opens at 12 o'clock
const BAND_INNER = 120;
const BAND_OUTER = 330;
const R_HUB = 150;
const R_AGENT = 205;
const R_PEOPLE = 278;
const R_RING_A = 250; // two sub-rings when a department has >8 people
const R_RING_B = 305;
const R_DEPT_LABEL = 346;
const DIM = 0.12;
const FALLBACK_COLOR = "#5b8cff";

const NODE_TRANSITION = { transition: "opacity 300ms ease, transform 300ms ease" } as const;

type Sector = { dept: OrgDepartment; a0: number; a1: number; mid: number };
type PersonNode = { person: OrgPerson; x: number; y: number; r: number };
type AgentNode = { agent: OrgAgentCard; x: number; y: number; homeKey: string };
type Selection = { kind: "person" | "agent" | "dept"; id: string } | null;
type ProfileTab = "overview" | "access";
type Tip = { x: number; y: number; title: string; sub: string };

const polar = (angle: number, r: number) => ({ x: CX + r * Math.cos(angle), y: CY + r * Math.sin(angle) });

function computeSectors(departments: OrgDepartment[]): Sector[] {
  const ordered = [...departments].sort((a, b) => a.sort - b.sort);
  const weights = ordered.map((d) => Math.max(d.head_count, 2));
  const total = weights.reduce((sum, w) => sum + w, 0) || 1;
  const usable = TAU - SECTOR_GAP * ordered.length;
  let angle = START_ANGLE;
  return ordered.map((dept, i) => {
    const span = (usable * weights[i]) / total;
    const sector = { dept, a0: angle, a1: angle + span, mid: angle + span / 2 };
    angle += span + SECTOR_GAP;
    return sector;
  });
}

function bandPath({ a0, a1 }: Sector): string {
  const large = a1 - a0 > Math.PI ? 1 : 0;
  const o0 = polar(a0, BAND_OUTER);
  const o1 = polar(a1, BAND_OUTER);
  const i1 = polar(a1, BAND_INNER);
  const i0 = polar(a0, BAND_INNER);
  return [
    `M ${o0.x.toFixed(2)} ${o0.y.toFixed(2)}`,
    `A ${BAND_OUTER} ${BAND_OUTER} 0 ${large} 1 ${o1.x.toFixed(2)} ${o1.y.toFixed(2)}`,
    `L ${i1.x.toFixed(2)} ${i1.y.toFixed(2)}`,
    `A ${BAND_INNER} ${BAND_INNER} 0 ${large} 0 ${i0.x.toFixed(2)} ${i0.y.toFixed(2)}`,
    "Z",
  ].join(" ");
}

function layoutPeople(sectors: Sector[], people: OrgPerson[]): PersonNode[] {
  const nodes: PersonNode[] = [];
  for (const s of sectors) {
    const members = people.filter((p) => p.department_key === s.dept.key);
    const n = members.length;
    if (n === 0) continue;
    const span = s.a1 - s.a0;
    const inset = span * 0.08 + 0.03;
    const usable = span - inset * 2;
    members.forEach((person, i) => {
      const angle = n === 1 ? s.mid : s.a0 + inset + (usable * (i + 0.5)) / n;
      const radius = n > 8 ? (i % 2 === 0 ? R_RING_A : R_RING_B) : R_PEOPLE;
      const lead = person.role_tier === "owner" || person.role_tier === "exec";
      const { x, y } = polar(angle, radius);
      nodes.push({ person, x, y, r: lead ? 18 : 14 });
    });
  }
  return nodes;
}

function layoutAgents(sectors: Sector[], agents: OrgAgentCard[]): AgentNode[] {
  const byHome = new Map<string, OrgAgentCard[]>();
  for (const a of agents) {
    const home = a.dept_keys[0];
    if (!home) continue;
    byHome.set(home, [...(byHome.get(home) ?? []), a]);
  }
  const nodes: AgentNode[] = [];
  for (const s of sectors) {
    const group = byHome.get(s.dept.key);
    if (!group) continue;
    group.forEach((agent, i) => {
      // Fan agents sharing a home sector around the bisector so they never overlap.
      const offset = (i - (group.length - 1) / 2) * 0.32;
      const { x, y } = polar(s.mid + offset, R_AGENT);
      nodes.push({ agent, x, y, homeKey: s.dept.key });
    });
  }
  return nodes;
}

const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).map((w) => w[0]).slice(0, 2).join("").toUpperCase();

const chip = (color: string) => ({ color, backgroundColor: `${color}1f`, borderColor: `${color}40` });

function Lock() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="5" y="10.5" width="14" height="9.5" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 10.5V8a4 4 0 1 1 8 0v2.5" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

export default function OrgBrainView({ token }: { token: string }) {
  const [data, setData] = useState<OrgOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState<Selection>(null);
  const [tip, setTip] = useState<Tip | null>(null);
  const [profile, setProfile] = useState<OrgPersonProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [tab, setTab] = useState<ProfileTab>("overview");
  const [entered, setEntered] = useState(false);
  const [animate, setAnimate] = useState(true);
  // 3D sphere vs 2D wheel. Default to the safe SSR value (2D), then upgrade on the client once we
  // know WebGL is available and the user hasn't asked to reduce motion.
  const [view, setView] = useState<OrgView>("2d");
  const [webglOK, setWebglOK] = useState(false);
  const [motionOK, setMotionOK] = useState(true);
  // Latest profile request wins (rapid manager → report navigation).
  const profileReq = useRef(0);

  useEffect(() => {
    const capable = detectWebGL();
    const reduced = prefersReducedMotion();
    setWebglOK(capable);
    setMotionOK(!reduced);
    // Default to the classic 2D org chart (Alex: "the sphere is messy; I prefer the classic 2D org
    // chart"). The 3D sphere stays a one-click opt-in via the toggle, and a returning user who picked
    // it keeps their choice (stored preference wins, only when WebGL is still available).
    let initial: OrgView = "2d";
    try {
      const stored = window.localStorage.getItem("orgView");
      if (capable && (stored === "2d" || stored === "3d")) initial = stored;
    } catch {
      /* localStorage unavailable — keep the 2D default */
    }
    if (!capable) initial = "2d";
    setView(initial);
  }, []);

  const chooseView = useCallback(
    (next: OrgView) => {
      if (next === "3d" && !webglOK) return;
      setView(next);
      try {
        window.localStorage.setItem("orgView", next);
      } catch {
        /* ignore persistence failures */
      }
    },
    [webglOK],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getOrgOverview(token));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the organization");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  // Entrance fade once the overview arrives — skipped under prefers-reduced-motion.
  useEffect(() => {
    if (!data) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setAnimate(false);
      setEntered(true);
      return;
    }
    const id = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(id);
  }, [data]);

  const clearSelection = useCallback(() => {
    setSel(null);
    setProfile(null);
    setProfileError(null);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") clearSelection();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [clearSelection]);

  const selectPerson = useCallback(
    async (id: string) => {
      const reqId = ++profileReq.current;
      setSel({ kind: "person", id });
      setTab("overview");
      setProfile(null);
      setProfileError(null);
      setProfileLoading(true);
      try {
        const res = await getOrgPerson(token, id);
        if (profileReq.current === reqId) setProfile(res);
      } catch (e) {
        if (profileReq.current === reqId)
          setProfileError(e instanceof Error ? e.message : "Could not load this profile");
      } finally {
        if (profileReq.current === reqId) setProfileLoading(false);
      }
    },
    [token],
  );

  // Manager/director grants or revokes one AI agent for this person. Picks the minimal override:
  // turning on a default-on agent just clears any revoke; turning off a default-off clears a grant.
  const manageAgent = async (personId: string, s: AgentState) => {
    const targetOn = !s.enabled;
    const mode: AgentOverrideMode = targetOn ? (s.default ? "default" : "grant") : s.default ? "revoke" : "default";
    try {
      await setPersonAgent(token, personId, s.agent, mode);
      void selectPerson(personId); // re-read so the toggles + spotlight reflect the new state
    } catch (e) {
      setProfileError(e instanceof Error ? e.message : "Could not update access");
    }
  };

  function selectAgent(key: string) {
    setProfile(null);
    setProfileError(null);
    setSel({ kind: "agent", id: key });
  }

  function toggleDept(key: string) {
    setProfile(null);
    setProfileError(null);
    setSel((prev) => (prev?.kind === "dept" && prev.id === key ? null : { kind: "dept", id: key }));
  }

  const sectors = useMemo(() => (data ? computeSectors(data.departments) : []), [data]);
  const personNodes = useMemo(() => (data ? layoutPeople(sectors, data.people) : []), [data, sectors]);
  const agentNodes = useMemo(() => (data ? layoutAgents(sectors, data.agents) : []), [data, sectors]);
  const deptColor = useMemo(() => {
    const m: Record<string, string> = {};
    for (const d of data?.departments ?? []) m[d.key] = d.color;
    return m;
  }, [data]);
  const deptName = useMemo(() => {
    const m: Record<string, string> = {};
    for (const d of data?.departments ?? []) m[d.key] = d.name;
    return m;
  }, [data]);
  const agentLabel = useMemo(() => {
    const m: Record<string, string> = {};
    for (const a of data?.agents ?? []) m[a.key] = a.label;
    return m;
  }, [data]);
  const hubPos = useMemo(() => {
    const m: Record<string, { x: number; y: number }> = {};
    for (const s of sectors) m[s.dept.key] = polar(s.mid, R_HUB);
    return m;
  }, [sectors]);

  // Connected sets driving the selection dim — shared with the 3D sphere via lib/orgFocus.
  const focus = useMemo(() => {
    if (!data || !sel) return null;
    return computeFocus(data, {
      personId: sel.kind === "person" ? sel.id : null,
      agentKey: sel.kind === "agent" ? sel.id : null,
      deptKey: sel.kind === "dept" ? sel.id : null,
    });
  }, [data, sel]);

  const q = query.trim().toLowerCase();
  const personAlpha = (p: OrgPerson): number => {
    if (focus) return focus.people.has(p.id) ? 1 : DIM;
    if (q) return p.full_name.toLowerCase().includes(q) || p.title.toLowerCase().includes(q) ? 1 : DIM;
    return 1;
  };
  const deptAlpha = (key: string): number => (focus ? (focus.depts.has(key) ? 1 : DIM) : 1);
  const agentAlpha = (key: string): number => (focus ? (focus.agents.has(key) ? 1 : DIM) : 1);

  if (loading && !data) {
    return (
      <div className="panel grid place-items-center px-6 py-20 text-zinc-500">
        <Spinner />
        <span className="mt-3 text-sm">Loading your organization…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
        {error}
        <button className="ml-3 underline underline-offset-2" onClick={() => void load()}>Retry</button>
      </div>
    );
  }

  if (!data || data.people.length === 0) {
    return (
      <EmptyState
        title="No organization seeded for this tenant"
        body="Once a roster is loaded, every person, department, and agent shows up here — with what the AI knows about each."
        busy={loading}
        onRun={() => void load()}
      />
    );
  }

  const selectedPerson = sel?.kind === "person" ? data.people.find((p) => p.id === sel.id) ?? null : null;
  const selectedAgent = sel?.kind === "agent" ? data.agents.find((a) => a.key === sel.id) ?? null : null;
  const mgr = profile?.manager ?? null;

  return (
    <div className="flex flex-col gap-4 xl:flex-row">
      {/* ---- explorer panel ---- */}
      <aside className="panel w-full shrink-0 p-5 xl:w-[260px]">
        <h2 className="text-sm font-semibold text-zinc-100">{data.company.name}</h2>
        <p className="label mt-1">
          {data.company.employee_count} employees · {data.company.provider}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-zinc-500">
          <span>
            People <span className="num font-medium text-zinc-200">{data.people.length}</span>
          </span>
          <span>·</span>
          <span>
            Departments <span className="num font-medium text-zinc-200">{data.departments.length}</span>
          </span>
          <span>·</span>
          <span>
            AI Agents <span className="num font-medium text-zinc-200">{data.agents.length}</span>
          </span>
        </div>
        <input
          className="field mt-4"
          placeholder="Search people or titles…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="label mb-2 mt-5">Departments</div>
        <ul className="space-y-1">
          {sectors.map(({ dept }) => (
            <li key={dept.key}>
              <button
                onClick={() => toggleDept(dept.key)}
                className={`flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left text-sm transition ${
                  sel?.kind === "dept" && sel.id === dept.key
                    ? "bg-white/[0.06] text-zinc-100"
                    : "text-zinc-400 hover:bg-white/[0.04] hover:text-zinc-200"
                }`}
              >
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: dept.color }} />
                <span className="flex-1 truncate">{dept.name}</span>
                <span className="num text-xs text-zinc-500">{dept.head_count}</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      {/* ---- graph (3D sphere / 2D wheel) ---- */}
      <div className="panel relative min-w-0 flex-1 overflow-hidden p-2">
        <div className="absolute right-3 top-3 z-30 inline-flex rounded-xl border border-white/[0.08] bg-ink-900/80 p-1 backdrop-blur">
          {(["2d", "3d"] as const).map((v) => {
            const disabled = v === "3d" && !webglOK;
            return (
              <button
                key={v}
                disabled={disabled}
                onClick={() => chooseView(v)}
                title={disabled ? "3D needs WebGL — unavailable on this device" : undefined}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                  view === v
                    ? "bg-accent/15 text-accent"
                    : disabled
                      ? "cursor-not-allowed text-zinc-600"
                      : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {v === "3d" ? "Sphere 3D" : "Classic 2D"}
              </button>
            );
          })}
        </div>

        {view === "3d" && webglOK ? (
          <div
            className="relative w-full"
            style={{ aspectRatio: "1000 / 760" }}
            role="img"
            aria-label={`Organization sphere — ${data.company.name}: ${data.people.length} people across ${data.departments.length} departments. Use the department list to browse, or switch to Classic 2D.`}
          >
            <OrgSphereLazy
              data={data}
              selectedPersonId={sel?.kind === "person" ? sel.id : null}
              selectedAgentKey={sel?.kind === "agent" ? sel.id : null}
              selectedDeptKey={sel?.kind === "dept" ? sel.id : null}
              query={query}
              motionOK={motionOK}
              onSelectPerson={(id) => void selectPerson(id)}
              onSelectAgent={selectAgent}
              onSelectDept={toggleDept}
              onClearSelection={clearSelection}
            />
          </div>
        ) : (
        <div className="relative w-full" style={{ aspectRatio: "1000 / 760" }}>
          <svg viewBox="0 0 1000 760" className="h-full w-full" onClick={clearSelection} role="img" aria-label="Organization graph">
            <g style={{ opacity: entered ? 1 : 0, transition: animate ? "opacity 500ms ease" : "none" }}>
              {/* sector bands */}
              {sectors.map((s) => (
                <path
                  key={`band-${s.dept.key}`}
                  d={bandPath(s)}
                  fill={s.dept.color}
                  fillOpacity={0.08}
                  className="cursor-pointer"
                  style={{ ...NODE_TRANSITION, opacity: deptAlpha(s.dept.key) }}
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleDept(s.dept.key);
                  }}
                />
              ))}

              {/* spokes: company → dept hubs */}
              {sectors.map((s) => {
                const hub = hubPos[s.dept.key];
                return (
                  <line
                    key={`spoke-${s.dept.key}`}
                    x1={CX} y1={CY} x2={hub.x} y2={hub.y}
                    stroke={s.dept.color} strokeOpacity={0.35} strokeWidth={1}
                    style={{ ...NODE_TRANSITION, opacity: deptAlpha(s.dept.key) }}
                  />
                );
              })}

              {/* edges: dept hub → each person */}
              {personNodes.map(({ person, x, y }) => {
                const hub = hubPos[person.department_key];
                if (!hub) return null;
                const color = deptColor[person.department_key] ?? FALLBACK_COLOR;
                const a = Math.min(personAlpha(person), deptAlpha(person.department_key));
                return (
                  <line
                    key={`edge-${person.id}`}
                    x1={hub.x} y1={hub.y} x2={x} y2={y}
                    stroke={color} strokeOpacity={0.25} strokeWidth={0.75}
                    style={{ ...NODE_TRANSITION, opacity: a }}
                  />
                );
              })}

              {/* dashed edges: agent → the dept hubs it serves */}
              {agentNodes.map(({ agent, x, y }) =>
                agent.dept_keys.map((dk, i) => {
                  const hub = hubPos[dk];
                  if (!hub) return null;
                  return (
                    <line
                      key={`agent-edge-${agent.key}-${dk}`}
                      x1={x} y1={y} x2={hub.x} y2={hub.y}
                      stroke={deptColor[dk] ?? FALLBACK_COLOR}
                      strokeOpacity={i === 0 ? 0.45 : 0.2}
                      strokeWidth={1}
                      strokeDasharray="4 3"
                      style={{ ...NODE_TRANSITION, opacity: agentAlpha(agent.key) }}
                    />
                  );
                }),
              )}

              {/* company node */}
              <g style={NODE_TRANSITION}>
                <rect
                  x={CX - 100} y={CY - 34} width={200} height={68} rx={18}
                  fill={FALLBACK_COLOR} fillOpacity={0.1}
                  stroke={FALLBACK_COLOR} strokeOpacity={0.45}
                />
                <text x={CX} y={CY - 6} textAnchor="middle" fontSize={14} fontWeight={700} fill="currentColor" className="select-none text-zinc-100">
                  {data.company.name}
                </text>
                <text x={CX} y={CY + 15} textAnchor="middle" fontSize={11} fill="currentColor" className="select-none text-zinc-500">
                  {data.company.employee_count} employees
                </text>
              </g>

              {/* dept hubs + sector labels */}
              {sectors.map((s) => {
                const hub = hubPos[s.dept.key];
                const label = polar(s.mid, R_DEPT_LABEL);
                return (
                  <g key={`hub-${s.dept.key}`} style={{ ...NODE_TRANSITION, opacity: deptAlpha(s.dept.key) }}>
                    <g
                      className="cursor-pointer"
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleDept(s.dept.key);
                      }}
                      onMouseEnter={() => setTip({ x: hub.x, y: hub.y + 16, title: s.dept.name, sub: `${s.dept.head_count} people` })}
                      onMouseLeave={() => setTip(null)}
                    >
                      <circle cx={hub.x} cy={hub.y} r={16} fill={s.dept.color} fillOpacity={0.92} />
                      <text x={hub.x} y={hub.y + 0.5} textAnchor="middle" dominantBaseline="middle" fontSize={10} fontWeight={700} fill="#0c0e13" className="select-none">
                        {s.dept.head_count}
                      </text>
                    </g>
                    <text x={label.x} y={label.y} textAnchor="middle" dominantBaseline="middle" fontSize={11} fontWeight={600} fill={s.dept.color} className="select-none">
                      {s.dept.name}
                    </text>
                  </g>
                );
              })}

              {/* agent nodes (rounded squares) */}
              {agentNodes.map(({ agent, x, y, homeKey }) => {
                const color = deptColor[homeKey] ?? FALLBACK_COLOR;
                return (
                  <g
                    key={`agent-${agent.key}`}
                    className="cursor-pointer"
                    style={{ ...NODE_TRANSITION, opacity: agentAlpha(agent.key) }}
                    onClick={(e) => {
                      e.stopPropagation();
                      selectAgent(agent.key);
                    }}
                    onMouseEnter={() => setTip({ x, y: y + 11, title: agent.label, sub: "AI agent" })}
                    onMouseLeave={() => setTip(null)}
                  >
                    <rect x={x - 9} y={y - 9} width={18} height={18} rx={5} fill={color} fillOpacity={0.3} stroke={color} strokeWidth={1.2} />
                    <text x={x} y={y + 0.5} textAnchor="middle" dominantBaseline="middle" fontSize={10} fill={color} className="select-none">
                      ✦
                    </text>
                  </g>
                );
              })}

              {/* person nodes */}
              {personNodes.map(({ person, x, y, r }) => {
                const color = deptColor[person.department_key] ?? FALLBACK_COLOR;
                const lead = person.role_tier === "owner" || person.role_tier === "exec";
                const selected = sel?.kind === "person" && sel.id === person.id;
                return (
                  <g
                    key={person.id}
                    className="cursor-pointer"
                    style={{ ...NODE_TRANSITION, opacity: personAlpha(person) }}
                    onClick={(e) => {
                      e.stopPropagation();
                      void selectPerson(person.id);
                    }}
                    onMouseEnter={() => setTip({ x, y: y + r, title: person.full_name, sub: person.title })}
                    onMouseLeave={() => setTip(null)}
                  >
                    {lead && <circle cx={x} cy={y} r={r + 3.5} fill="none" stroke={color} strokeWidth={1} strokeOpacity={0.5} />}
                    <circle cx={x} cy={y} r={r} fill={color} fillOpacity={selected ? 0.35 : 0.2} stroke={color} strokeWidth={1.5} />
                    <text x={x} y={y + 0.5} textAnchor="middle" dominantBaseline="middle" fontSize={r >= 18 ? 11 : 9.5} fontWeight={600} fill={color} className="select-none">
                      {initials(person.full_name)}
                    </text>
                    {person.role_tier === "owner" && (
                      <text x={x} y={y + r + 13} textAnchor="middle" fontSize={7.5} fontWeight={700} letterSpacing={1.5} fill={color} className="select-none">
                        OWNER
                      </text>
                    )}
                  </g>
                );
              })}
            </g>
          </svg>

          {tip && (
            <div
              className="panel pointer-events-none absolute z-10 px-2.5 py-1.5"
              style={{ left: `${(tip.x / 10).toFixed(2)}%`, top: `${(tip.y / 7.6).toFixed(2)}%`, transform: "translate(-50%, 10px)" }}
            >
              <div className="whitespace-nowrap text-xs font-medium text-zinc-100">{tip.title}</div>
              <div className="whitespace-nowrap text-[11px] text-zinc-500">{tip.sub}</div>
            </div>
          )}
        </div>
        )}

        {/* ---- person profile panel ---- */}
        {selectedPerson && (
          <div className="panel absolute bottom-3 right-3 top-3 z-20 w-[340px] max-w-[88%] overflow-auto p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div
                  className="grid h-11 w-11 shrink-0 place-items-center rounded-full text-sm font-semibold"
                  style={{
                    color: deptColor[selectedPerson.department_key] ?? FALLBACK_COLOR,
                    backgroundColor: `${deptColor[selectedPerson.department_key] ?? FALLBACK_COLOR}26`,
                    boxShadow: `inset 0 0 0 1.5px ${deptColor[selectedPerson.department_key] ?? FALLBACK_COLOR}66`,
                  }}
                >
                  {initials(selectedPerson.full_name)}
                </div>
                <div>
                  <div className="text-sm font-semibold text-zinc-100">{selectedPerson.full_name}</div>
                  <div className="text-xs text-zinc-500">{selectedPerson.title}</div>
                </div>
              </div>
              <button className="btn-ghost !px-2 !py-1 text-xs" onClick={clearSelection} aria-label="Close profile">
                ✕
              </button>
            </div>

            <div className="mt-3 flex flex-wrap gap-1.5">
              <span className="inline-flex rounded-md border px-2 py-0.5 text-[11px] font-medium" style={chip(deptColor[selectedPerson.department_key] ?? FALLBACK_COLOR)}>
                {deptName[selectedPerson.department_key] ?? selectedPerson.department_key}
              </span>
              <span className="inline-flex rounded-md border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-zinc-400">
                {selectedPerson.role_tier}
              </span>
            </div>

            <div className="mt-4 inline-flex rounded-xl border border-white/[0.08] bg-ink-900/70 p-1">
              {(["overview", "access"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                    tab === t ? "bg-accent/15 text-accent" : "text-zinc-500 hover:text-zinc-300"
                  }`}
                >
                  {t === "overview" ? "Overview" : "AI Access"}
                </button>
              ))}
            </div>

            {profileLoading ? (
              <div className="grid place-items-center py-10 text-zinc-500">
                <Spinner />
              </div>
            ) : profileError ? (
              <p className="mt-4 text-sm text-red-300">{profileError}</p>
            ) : profile ? (
              tab === "overview" ? (
                <div>
                  <div className="label mb-1.5 mt-4">What the AI knows</div>
                  <p className="text-[13px] leading-relaxed text-zinc-300">{profile.person.ai_context}</p>
                  {mgr && (
                    <>
                      <div className="label mb-1.5 mt-4">Reports to</div>
                      <button
                        className="flex w-full items-center justify-between gap-2 rounded-lg border border-white/[0.06] px-3 py-2 text-left transition hover:bg-white/[0.04]"
                        onClick={() => void selectPerson(mgr.id)}
                      >
                        <span className="text-[13px] font-medium text-zinc-100">{mgr.full_name}</span>
                        <span className="truncate text-xs text-zinc-500">{mgr.title}</span>
                      </button>
                    </>
                  )}
                  {profile.direct_reports.length > 0 && (
                    <>
                      <div className="label mb-1.5 mt-4">Direct reports · {profile.direct_reports.length}</div>
                      <ul className="space-y-1">
                        {profile.direct_reports.map((d) => (
                          <li key={d.id}>
                            <button
                              className="flex w-full items-center justify-between gap-2 rounded-lg border border-white/[0.06] px-3 py-2 text-left transition hover:bg-white/[0.04]"
                              onClick={() => void selectPerson(d.id)}
                            >
                              <span className="text-[13px] font-medium text-zinc-100">{d.full_name}</span>
                              <span className="truncate text-xs text-zinc-500">{d.title}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              ) : (
                <div>
                  <div className="label mb-1.5 mt-4">
                    {profile.ai_access.can_manage ? "AI agent access — tap to grant or revoke" : "Agents this person can use"}
                  </div>
                  {profile.ai_access.can_manage && profile.ai_access.agent_states ? (
                    <div className="space-y-1">
                      {profile.ai_access.agent_states.map((s) => {
                        const home = data.agents.find((x) => x.key === s.agent)?.dept_keys[0];
                        const c = (home ? deptColor[home] : undefined) ?? FALLBACK_COLOR;
                        return (
                          <button
                            key={s.agent}
                            onClick={() => void manageAgent(selectedPerson.id, s)}
                            className="flex w-full items-center justify-between gap-2 rounded-lg border border-white/[0.06] px-3 py-2 text-left transition hover:bg-white/[0.04]"
                          >
                            <span className="flex items-center gap-2 text-[13px] text-zinc-200">
                              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: c }} />
                              {agentLabel[s.agent] ?? s.agent}
                              {s.overridden && (
                                <span className="text-[9px] font-semibold uppercase tracking-wide text-amber-300/80">override</span>
                              )}
                            </span>
                            <span className={`relative h-5 w-9 shrink-0 rounded-full transition ${s.enabled ? "bg-emerald-500/70" : "bg-white/10"}`}>
                              <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${s.enabled ? "left-[18px]" : "left-0.5"}`} />
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  ) : profile.ai_access.agents.length === 0 ? (
                    <p className="text-[13px] text-zinc-500">No agents granted.</p>
                  ) : (
                    <div className="flex flex-wrap gap-1.5">
                      {profile.ai_access.agents.map((k) => {
                        const home = data.agents.find((x) => x.key === k)?.dept_keys[0];
                        const c = (home ? deptColor[home] : undefined) ?? FALLBACK_COLOR;
                        return (
                          <span key={k} className="inline-flex rounded-md border px-2 py-0.5 text-[11px] font-medium" style={chip(c)}>
                            {agentLabel[k] ?? k}
                          </span>
                        );
                      })}
                    </div>
                  )}
                  <div className="label mb-1.5 mt-4">Sections</div>
                  <p className="text-xs text-zinc-400">{profile.ai_access.sections.join(" · ")}</p>
                  {profile.ai_access.not_accessible.length > 0 && (
                    <>
                      <div className="label mb-1.5 mt-4">Not accessible</div>
                      <ul className="space-y-1.5">
                        {profile.ai_access.not_accessible.map((k) => (
                          <li key={k} className="flex items-center gap-2 text-[13px] text-zinc-500">
                            <Lock />
                            <span>{agentLabel[k] ?? k}</span>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                  {(() => {
                    const acc = computeDeptAccess(selectedPerson, data.departments.map((d) => d.key));
                    return (
                      <>
                        <div className="label mb-1.5 mt-4">Department access</div>
                        <div className="flex flex-wrap gap-1.5">
                          {acc.accessibleDepts.map((k) => (
                            <span key={k} className="inline-flex rounded-md border px-2 py-0.5 text-[11px] font-medium" style={chip(deptColor[k] ?? FALLBACK_COLOR)}>
                              ✓ {deptName[k] ?? k}
                            </span>
                          ))}
                        </div>
                        {acc.isolatedDepts.length > 0 && (
                          <>
                            <div className="label mb-1.5 mt-4 text-red-300/70">Isolated from</div>
                            <div className="flex flex-wrap gap-1.5">
                              {acc.isolatedDepts.map((k) => (
                                <span key={k} className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-white/[0.03] px-2 py-0.5 text-[11px] font-medium text-zinc-500">
                                  <Lock />
                                  {deptName[k] ?? k}
                                </span>
                              ))}
                            </div>
                            <p className="mt-2 text-[11px] leading-relaxed text-zinc-500">{acc.isolationReason}</p>
                          </>
                        )}
                      </>
                    );
                  })()}
                </div>
              )
            ) : null}
          </div>
        )}

        {/* ---- agent card panel ---- */}
        {selectedAgent && (
          <div className="panel absolute bottom-3 right-3 top-3 z-20 w-[340px] max-w-[88%] overflow-auto p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div
                  className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border text-base"
                  style={chip((selectedAgent.dept_keys[0] ? deptColor[selectedAgent.dept_keys[0]] : undefined) ?? FALLBACK_COLOR)}
                >
                  ✦
                </div>
                <div>
                  <div className="text-sm font-semibold text-zinc-100">{selectedAgent.label}</div>
                  <div className="text-xs text-zinc-500">AI agent</div>
                </div>
              </div>
              <button className="btn-ghost !px-2 !py-1 text-xs" onClick={clearSelection} aria-label="Close agent card">
                ✕
              </button>
            </div>
            <p className="mt-4 text-[13px] leading-relaxed text-zinc-300">{selectedAgent.description}</p>
            <div className="label mb-1.5 mt-4">Serves</div>
            <div className="flex flex-wrap gap-1.5">
              {selectedAgent.dept_keys.map((dk) => (
                <span key={dk} className="inline-flex rounded-md border px-2 py-0.5 text-[11px] font-medium" style={chip(deptColor[dk] ?? FALLBACK_COLOR)}>
                  {deptName[dk] ?? dk}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
