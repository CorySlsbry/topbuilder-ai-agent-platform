"use client";

// A classic top-down 2D org chart (boxes + reporting-line connectors), built straight from an
// OrgOverview. This is the "classic 2D org chart" Alex asked for (vs. the radial wheel in
// OrgBrainView or the 3D sphere) — leadership at the top, then department heads, then their reports
// grouped by department. Pure presentational: deterministic layout, no data fetching, theme-neutral
// inline styling so it reads on both the demo's dark canvas and inside a Panel.
//
// Reused by app/demo (default view, toggle to 3D). Selection is reported up via onSelectPerson so the
// host can drive the same profile drawer the sphere uses.

import { useMemo } from "react";

import type { OrgOverview, OrgPerson } from "@/lib/types";

const FALLBACK_COLOR = "#5b8cff";
const LEADERSHIP_TIERS = new Set(["owner", "exec"]);

const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).map((w) => w[0]).slice(0, 2).join("").toUpperCase();

type DeptColumn = {
  key: string;
  name: string;
  color: string;
  head: OrgPerson | null;
  members: OrgPerson[]; // non-head members of the department
};

/** Group people into department columns; the lowest-sorted leadership person is the org head. */
function buildColumns(data: OrgOverview): { leaders: OrgPerson[]; columns: DeptColumn[] } {
  const byDept = new Map<string, OrgPerson[]>();
  for (const p of data.people) {
    byDept.set(p.department_key, [...(byDept.get(p.department_key) ?? []), p]);
  }
  const ordered = [...data.departments].sort((a, b) => a.sort - b.sort);

  // Org-level leaders (owner/exec with no manager) float to the top row.
  const leaders = data.people
    .filter((p) => LEADERSHIP_TIERS.has(p.role_tier) && !p.manager_id)
    .sort((a, b) => (a.role_tier === "owner" ? -1 : 1) - (b.role_tier === "owner" ? -1 : 1));
  const leaderIds = new Set(leaders.map((l) => l.id));

  const columns: DeptColumn[] = ordered.map((d) => {
    const all = (byDept.get(d.key) ?? []).filter((p) => !leaderIds.has(p.id));
    // The department "head": prefer the exec/owner, else a lead, else the first member.
    const head =
      all.find((p) => LEADERSHIP_TIERS.has(p.role_tier)) ??
      all.find((p) => p.role_tier === "lead") ??
      all[0] ??
      null;
    const members = all.filter((p) => p.id !== head?.id);
    return { key: d.key, name: d.name, color: d.color || FALLBACK_COLOR, head, members };
  });

  return { leaders, columns };
}

function PersonCard({
  person,
  color,
  selected,
  onSelect,
  size = "md",
}: {
  person: OrgPerson;
  color: string;
  selected: boolean;
  onSelect: (id: string) => void;
  size?: "lg" | "md" | "sm";
}) {
  const pad = size === "lg" ? "10px 14px" : size === "sm" ? "6px 9px" : "8px 11px";
  const avatar = size === "lg" ? 36 : size === "sm" ? 22 : 28;
  const nameSize = size === "lg" ? 14 : size === "sm" ? 12 : 13;
  return (
    <button
      type="button"
      onClick={() => onSelect(person.id)}
      title={`${person.full_name} · ${person.title}`}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 9,
        width: "100%",
        textAlign: "left",
        cursor: "pointer",
        padding: pad,
        borderRadius: 11,
        border: `1px solid ${selected ? `${color}` : "rgba(255,255,255,0.08)"}`,
        background: selected ? `${color}1f` : "rgba(255,255,255,0.03)",
        borderLeft: `3px solid ${color}`,
        transition: "background 150ms ease, border-color 150ms ease",
      }}
    >
      <span
        style={{
          flexShrink: 0,
          width: avatar,
          height: avatar,
          borderRadius: "50%",
          display: "grid",
          placeItems: "center",
          fontWeight: 700,
          fontSize: avatar * 0.36,
          color,
          background: `${color}26`,
          boxShadow: `inset 0 0 0 1.5px ${color}66`,
        }}
      >
        {initials(person.full_name)}
      </span>
      <span style={{ minWidth: 0 }}>
        <span
          style={{
            display: "block",
            fontWeight: 600,
            fontSize: nameSize,
            color: "var(--chart-fg, #f4f6fb)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {person.full_name}
        </span>
        <span
          style={{
            display: "block",
            fontSize: nameSize - 2,
            color: "var(--chart-muted, #8b97ad)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {person.title}
        </span>
      </span>
    </button>
  );
}

export default function OrgChart2D({
  data,
  selectedPersonId,
  query,
  onSelectPerson,
}: {
  data: OrgOverview;
  selectedPersonId: string | null;
  query?: string;
  onSelectPerson: (id: string) => void;
}) {
  const { leaders, columns } = useMemo(() => buildColumns(data), [data]);
  const q = (query ?? "").trim().toLowerCase();
  const matches = (p: OrgPerson) =>
    !q || p.full_name.toLowerCase().includes(q) || p.title.toLowerCase().includes(q);
  const dim = (p: OrgPerson): number => (q && !matches(p) ? 0.28 : 1);

  return (
    <div style={{ width: "100%", overflowX: "auto", paddingBottom: 6 }}>
      <div style={{ minWidth: Math.max(640, columns.length * 220) }}>
        {/* Leadership row */}
        {leaders.length > 0 && (
          <div style={{ display: "flex", justifyContent: "center", gap: 14, flexWrap: "wrap", marginBottom: 6 }}>
            {leaders.map((l) => {
              const color = data.departments.find((d) => d.key === l.department_key)?.color ?? FALLBACK_COLOR;
              return (
                <div key={l.id} style={{ width: 260, maxWidth: "100%", opacity: dim(l) }}>
                  <PersonCard
                    person={l}
                    color={color}
                    selected={selectedPersonId === l.id}
                    onSelect={onSelectPerson}
                    size="lg"
                  />
                </div>
              );
            })}
          </div>
        )}

        {/* Connector trunk from leadership to the department columns */}
        {leaders.length > 0 && (
          <div style={{ height: 18, display: "flex", justifyContent: "center" }} aria-hidden>
            <div style={{ width: 1, background: "rgba(255,255,255,0.12)" }} />
          </div>
        )}

        {/* Department columns */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(${columns.length}, minmax(190px, 1fr))`,
            gap: 14,
            alignItems: "start",
          }}
        >
          {columns.map((col) => (
            <div key={col.key} style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
              {/* Department label */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 7,
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: 0.6,
                  textTransform: "uppercase",
                  color: col.color,
                  padding: "2px 2px 4px",
                }}
              >
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: col.color, flexShrink: 0 }} />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{col.name}</span>
                <span style={{ marginLeft: "auto", color: "var(--chart-muted, #8b97ad)", fontWeight: 600 }}>
                  {(col.head ? 1 : 0) + col.members.length}
                </span>
              </div>

              {col.head && (
                <div style={{ opacity: dim(col.head) }}>
                  <PersonCard
                    person={col.head}
                    color={col.color}
                    selected={selectedPersonId === col.head.id}
                    onSelect={onSelectPerson}
                    size="md"
                  />
                </div>
              )}

              {col.members.length > 0 && (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                    paddingLeft: 12,
                    borderLeft: "1px solid rgba(255,255,255,0.07)",
                    marginLeft: 6,
                  }}
                >
                  {col.members.map((m) => (
                    <div key={m.id} style={{ opacity: dim(m) }}>
                      <PersonCard
                        person={m}
                        color={col.color}
                        selected={selectedPersonId === m.id}
                        onSelect={onSelectPerson}
                        size="sm"
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
