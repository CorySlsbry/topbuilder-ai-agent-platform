"use client";

// Public demo of the Organization view (fixture data, no login needed). Open /demo. Defaults to the
// classic 2D org chart (Alex's preference) with a one-click toggle to the 3D sphere — drag to rotate,
// scroll/pinch to zoom. Click a person to open their profile + AI-access drawer; type to search.

import { useEffect, useMemo, useState, type CSSProperties } from "react";

import OrgChart2D from "@/components/OrgChart2D";
import OrgSphereLazy from "@/components/OrgSphereLazy";
import type { OrgAgentCard, OrgDepartment, OrgOverview, OrgPerson } from "@/lib/types";
import { computeAgentAccess, computeDeptAccess } from "@/lib/orgAccess";
import { detectWebGL } from "@/lib/webgl";

type DemoView = "2d" | "3d";

const DEPTS: { key: string; name: string; color: string; size: number }[] = [
  { key: "ops", name: "Operations", color: "#5b8cff", size: 62 },
  { key: "service", name: "Service", color: "#f87171", size: 80 },
  { key: "sales", name: "Sales", color: "#36d399", size: 44 },
  { key: "warehouse", name: "Warehouse", color: "#a78bfa", size: 34 },
  { key: "finance", name: "Finance", color: "#fbbf24", size: 20 },
  { key: "marketing", name: "Marketing", color: "#22d3ee", size: 18 },
  { key: "hr", name: "People", color: "#f472b6", size: 12 },
  { key: "admin", name: "Admin", color: "#94a3b8", size: 10 },
];

const FIRST = ["Avery", "Jordan", "Casey", "Riley", "Morgan", "Quinn", "Drew", "Sky", "Reese", "Sage", "Blake", "Devin", "Noa", "Wren", "Emery", "Rowan"];
const LAST = ["Nguyen", "Patel", "Garcia", "Smith", "Khan", "Lopez", "Brooks", "Reed", "Cole", "Hayes", "Ford", "Diaz", "Vance", "Osei", "Park", "Rossi"];

function buildFixture(): OrgOverview {
  const departments: OrgDepartment[] = DEPTS.map((d, i) => ({
    id: `dept-${d.key}`, key: d.key, name: d.name, color: d.color, sort: i, head_count: d.size,
  }));
  const people: OrgPerson[] = [];
  let n = 0;
  for (const d of DEPTS) {
    const headId = `p-${d.key}-0`;
    for (let i = 0; i < d.size; i++) {
      const id = `p-${d.key}-${i}`;
      const tier = i === 0 ? (d.key === "ops" ? "owner" : "exec") : i < 4 ? "lead" : "ic";
      people.push({
        id,
        full_name: `${FIRST[(n * 5) % FIRST.length]} ${LAST[(n * 7) % LAST.length]}`,
        title: i === 0 ? `${d.name} Director` : `${d.name} ${i < 4 ? "Lead" : "Specialist"}`,
        department_key: d.key,
        role_tier: tier,
        manager_id: i === 0 ? null : headId,
      });
      n++;
    }
  }
  const agents: OrgAgentCard[] = [
    { key: "workforce", label: "Workforce", dept_keys: ["ops"], description: "" },
    { key: "routing", label: "Dispatch", dept_keys: ["service", "ops"], description: "" },
    { key: "financial", label: "Financial", dept_keys: ["finance"], description: "" },
    { key: "inventory", label: "Inventory", dept_keys: ["warehouse"], description: "" },
    { key: "booking", label: "Booking", dept_keys: ["sales"], description: "" },
    { key: "documents", label: "Documents", dept_keys: ["admin"], description: "" },
  ];
  return {
    company: { name: "Canyon Ridge", employee_count: people.length, provider: "ServiceTitan" },
    departments, people, agents,
    caller_access: { department: null, allowed_agents: null },
  };
}

const initials = (name: string) => name.split(/\s+/).filter(Boolean).map((w) => w[0]).slice(0, 2).join("");
const sectionLabel: CSSProperties = { fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6, color: "#7e8aa3", margin: "15px 0 7px" };
const chip = (c: string): CSSProperties => ({
  display: "inline-flex", alignItems: "center", padding: "2px 9px", fontSize: 11.5, fontWeight: 500,
  borderRadius: 7, color: c, background: `${c}1f`, border: `1px solid ${c}40`,
});
const reportRow = (c: string): CSSProperties => ({
  display: "flex", alignItems: "center", gap: 8, width: "100%", textAlign: "left", cursor: "pointer",
  padding: "6px 9px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.06)", background: "rgba(255,255,255,0.02)",
  borderLeft: `2px solid ${c}`,
});

export default function SpherePreview() {
  const data = useMemo(buildFixture, []);
  const [sel, setSel] = useState<string>("none");
  const [query, setQuery] = useState("");
  // Default to the classic 2D org chart (Alex: "the sphere is messy; I prefer the classic 2D org
  // chart"). 3D stays a one-click opt-in, and only when WebGL is actually available.
  const [view, setView] = useState<DemoView>("2d");
  const [webglOK, setWebglOK] = useState(false);
  // Explicit pixel size — r3f v8 only starts its render loop once react-use-measure reports a
  // non-zero size, and a definite pixel size is the most reliable way to give it one.
  const [dim, setDim] = useState({ w: 1280, h: 760 });
  const [overrides, setOverrides] = useState<Record<string, Record<string, "grant" | "revoke">>>({});
  useEffect(() => {
    setWebglOK(detectWebGL());
    const update = () => setDim({ w: window.innerWidth, h: window.innerHeight });
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);
  const selLabel =
    sel === "none"
      ? "nothing selected"
      : sel.startsWith("person:")
        ? data.people.find((p) => p.id === sel.slice(7))?.full_name ?? sel
        : sel;

  const deptByKey = useMemo(() => Object.fromEntries(data.departments.map((d) => [d.key, d])), [data]);
  const allDeptKeys = useMemo(() => data.departments.map((d) => d.key), [data]);
  const allAgents = useMemo(() => data.agents.map((a) => ({ key: a.key, label: a.label })), [data]);

  const person = sel.startsWith("person:") ? data.people.find((p) => p.id === sel.slice(7)) ?? null : null;
  const access = person ? computeDeptAccess(person, allDeptKeys) : null;
  const agentAccess = person ? computeAgentAccess(person, allAgents) : null;
  const manager = person?.manager_id ? data.people.find((p) => p.id === person.manager_id) ?? null : null;
  const reports = person ? data.people.filter((p) => p.manager_id === person.id) : [];
  const pColor = person ? (deptByKey[person.department_key]?.color ?? "#5b8cff") : "#5b8cff";
  // Manager grant/revoke — simulated locally (the demo has no backend); persists in the live view.
  const toggleAgent = (pid: string, agentKey: string, enabled: boolean, defaultOn: boolean) => {
    setOverrides((prev) => {
      const po = { ...(prev[pid] || {}) };
      const targetOn = !enabled;
      if (targetOn === defaultOn) delete po[agentKey];
      else po[agentKey] = targetOn ? "grant" : "revoke";
      return { ...prev, [pid]: po };
    });
  };
  return (
    <div style={{ position: "fixed", top: 0, left: 0, width: dim.w, height: dim.h, background: "radial-gradient(80% 80% at 50% 40%, #0d1018 0%, #07080d 100%)" }}>
      <div
        style={{
          position: "absolute", left: 16, top: 14, zIndex: 50, color: "#cdd7ee",
          font: "13px system-ui", display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap",
        }}
      >
        <strong style={{ color: "#fff" }}>Organization demo</strong>
        <span style={{ opacity: 0.7 }}>{data.people.length} people · 8 departments · 6 agents</span>
        <input
          placeholder="search people…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{ padding: "4px 10px", background: "#161b26", color: "#fff", border: "1px solid #2a3550", borderRadius: 7, outline: "none" }}
        />
        <div style={{ display: "inline-flex", gap: 2, padding: 3, borderRadius: 9, border: "1px solid #2a3550", background: "#10141d" }}>
          {(["2d", "3d"] as const).map((v) => {
            const disabled = v === "3d" && !webglOK;
            const activeView = view === v;
            return (
              <button
                key={v}
                type="button"
                disabled={disabled}
                onClick={() => setView(v)}
                title={disabled ? "3D needs WebGL — unavailable on this device" : undefined}
                style={{
                  padding: "4px 11px",
                  borderRadius: 7,
                  border: "none",
                  cursor: disabled ? "not-allowed" : "pointer",
                  fontSize: 12,
                  fontWeight: 600,
                  background: activeView ? "rgba(91,140,255,0.18)" : "transparent",
                  color: activeView ? "#9cb6ff" : disabled ? "#4a5468" : "#8b97ad",
                }}
              >
                {v === "2d" ? "Classic 2D" : "Sphere 3D"}
              </button>
            );
          })}
        </div>
        <span style={{ opacity: 0.7 }}>selected: {selLabel}</span>
      </div>
      <div style={{ position: "absolute", right: 16, bottom: 14, zIndex: 50, color: "#7e8aa3", font: "12px system-ui", textAlign: "right" }}>
        {view === "3d" && webglOK
          ? "drag = rotate · scroll / pinch = zoom · click a dot = select · type to search"
          : "click a person = open profile · type to search"}
      </div>
      {view === "3d" && webglOK ? (
        <OrgSphereLazy
          data={data}
          selectedPersonId={sel.startsWith("person:") ? sel.slice(7) : null}
          selectedAgentKey={sel.startsWith("agent:") ? sel.slice(6) : null}
          selectedDeptKey={sel.startsWith("dept:") ? sel.slice(5) : null}
          query={query}
          motionOK={true}
          onSelectPerson={(id) => setSel(`person:${id}`)}
          onSelectAgent={(k) => setSel(`agent:${k}`)}
          onSelectDept={(k) => setSel(`dept:${k}`)}
          onClearSelection={() => setSel("none")}
        />
      ) : (
        <div
          style={{
            position: "absolute",
            inset: 0,
            paddingTop: 64,
            paddingBottom: 16,
            paddingLeft: 18,
            paddingRight: person ? 376 : 18,
            overflowY: "auto",
          }}
        >
          <OrgChart2D
            data={data}
            selectedPersonId={sel.startsWith("person:") ? sel.slice(7) : null}
            query={query}
            onSelectPerson={(id) => setSel(`person:${id}`)}
          />
        </div>
      )}

      {person && access && agentAccess && (
        <div
          style={{
            position: "absolute", right: 16, top: 56, bottom: 16, width: 344, overflowY: "auto", zIndex: 60,
            background: "rgba(11,14,21,0.93)", border: "1px solid #1e2636", borderRadius: 14, padding: 18,
            color: "#dbe3f4", font: "13px system-ui", backdropFilter: "blur(8px)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ width: 44, height: 44, borderRadius: "50%", display: "grid", placeItems: "center", fontWeight: 700, color: pColor, background: `${pColor}26`, boxShadow: `inset 0 0 0 1.5px ${pColor}66` }}>
              {initials(person.full_name)}
            </div>
            <div>
              <div style={{ fontWeight: 600, color: "#fff", fontSize: 14 }}>{person.full_name}</div>
              <div style={{ color: "#8b97ad", fontSize: 12 }}>{person.title}</div>
            </div>
            <button onClick={() => setSel("none")} style={{ marginLeft: "auto", background: "none", border: "none", color: "#6b7790", cursor: "pointer", fontSize: 16 }}>✕</button>
          </div>

          <div style={{ display: "flex", gap: 6, marginTop: 11, flexWrap: "wrap" }}>
            <span style={chip(pColor)}>{deptByKey[person.department_key]?.name}</span>
            <span style={{ ...chip("#8b97ad"), textTransform: "uppercase", letterSpacing: 0.5 }}>{person.role_tier}</span>
            {access.isLeadership && <span style={chip("#fbbf24")}>Org-wide access</span>}
          </div>

          <div style={sectionLabel}>AI agent access — tap to grant or revoke</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {allAgents.map((a) => {
              const defaultOn = agentAccess.allowed.some((x) => x.key === a.key);
              const ov = overrides[person.id]?.[a.key];
              const on = ov === "grant" ? true : ov === "revoke" ? false : defaultOn;
              return (
                <button
                  key={a.key}
                  onClick={() => toggleAgent(person.id, a.key, on, defaultOn)}
                  style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, width: "100%",
                    cursor: "pointer", padding: "6px 9px", borderRadius: 8,
                    border: "1px solid rgba(255,255,255,0.06)", background: "rgba(255,255,255,0.02)",
                  }}
                >
                  <span style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, color: "#e6ecf8" }}>
                    <span style={{ width: 7, height: 7, borderRadius: "50%", background: pColor }} />
                    {a.label}
                    {ov && on !== defaultOn && (
                      <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#fcd34d" }}>
                        override
                      </span>
                    )}
                  </span>
                  <span style={{ position: "relative", height: 20, width: 36, borderRadius: 999, transition: "background .15s", background: on ? "rgba(16,185,129,0.7)" : "rgba(255,255,255,0.1)" }}>
                    <span style={{ position: "absolute", top: 2, left: on ? 18 : 2, height: 16, width: 16, borderRadius: "50%", background: "#fff", transition: "left .15s" }} />
                  </span>
                </button>
              );
            })}
          </div>
          <div style={{ marginTop: 7, fontSize: 11, color: "#6b7790", lineHeight: 1.4 }}>
            Demo: changes are simulated locally. In the live platform a manager&apos;s edits persist — audited and enforced server-side.
          </div>

          <div style={sectionLabel}>Department access</div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {access.accessibleDepts.map((k) => (
              <span key={k} style={chip(deptByKey[k]?.color ?? "#5b8cff")}>✓ {deptByKey[k]?.name ?? k}</span>
            ))}
          </div>
          {access.isolatedDepts.length > 0 && (
            <>
              <div style={{ ...sectionLabel, color: "#e0796f" }}>Isolated from</div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {access.isolatedDepts.map((k) => (
                  <span key={k} style={{ ...chip("#5b6577"), opacity: 0.9 }}>🔒 {deptByKey[k]?.name ?? k}</span>
                ))}
              </div>
              <div style={{ marginTop: 8, fontSize: 11.5, color: "#7e8aa3", lineHeight: 1.45 }}>{access.isolationReason}</div>
            </>
          )}

          {manager && (
            <>
              <div style={sectionLabel}>Reports to</div>
              <button onClick={() => setSel(`person:${manager.id}`)} style={reportRow(deptByKey[manager.department_key]?.color ?? "#5b8cff")}>
                <span style={{ color: "#e6ecf8", fontSize: 12.5 }}>{manager.full_name}</span>
                <span style={{ color: "#7e8aa3", fontSize: 11, marginLeft: "auto" }}>{manager.title}</span>
              </button>
            </>
          )}
          {reports.length > 0 && (
            <>
              <div style={sectionLabel}>
                Direct reports · {reports.length}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 240, overflowY: "auto" }}>
                {reports.map((r) => (
                  <button key={r.id} onClick={() => setSel(`person:${r.id}`)} style={reportRow(deptByKey[r.department_key]?.color ?? "#5b8cff")}>
                    <span style={{ width: 7, height: 7, borderRadius: "50%", background: deptByKey[r.department_key]?.color ?? "#5b8cff", flexShrink: 0 }} />
                    <span style={{ color: "#e6ecf8", fontSize: 12.5 }}>{r.full_name}</span>
                    <span style={{ color: "#7e8aa3", fontSize: 11, marginLeft: "auto", whiteSpace: "nowrap" }}>{r.title}</span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
