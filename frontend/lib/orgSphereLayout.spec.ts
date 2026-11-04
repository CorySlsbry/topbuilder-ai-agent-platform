import { describe, expect, it } from "vitest";

import type { OrgAgentCard, OrgDepartment, OrgPerson } from "@/lib/types";
import {
  angleBetween,
  buildOrgSphereLayout,
  R_AGENT,
  R_DEPT,
  R_PEOPLE,
  type Vec3,
} from "./orgSphereLayout";

const EPS = 1e-9;
const mag = (v: Vec3): number => Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);

function dept(key: string, sort: number, color: string, headCount: number): OrgDepartment {
  return { id: `dept-${key}`, key, name: key.toUpperCase(), color, sort, head_count: headCount };
}

function person(
  id: string,
  deptKey: string,
  roleTier = "ic",
  managerId: string | null = null,
): OrgPerson {
  return {
    id,
    full_name: `Person ${id}`,
    title: `Title ${id}`,
    department_key: deptKey,
    role_tier: roleTier,
    manager_id: managerId,
  };
}

const agentCard = (key: string, deptKeys: string[]): OrgAgentCard => ({
  key,
  label: key.toUpperCase(),
  dept_keys: deptKeys,
  description: `desc ${key}`,
});

/** A small, hand-specified org: 3 departments of different sizes, a lead in each, 3 agents. */
function scenario() {
  const departments = [
    dept("ops", 1, "#ff0000", 6),
    dept("sales", 2, "#00ff00", 2),
    dept("admin", 3, "#0000ff", 1),
  ];
  const people = [
    person("o1", "ops", "owner"),
    person("o2", "ops", "ic", "o1"),
    person("o3", "ops", "ic", "o1"),
    person("o4", "ops", "ic", "o1"),
    person("s1", "sales", "exec"),
    person("s2", "sales", "ic", "s1"),
    person("a1", "admin", "ic"),
  ];
  const agents = [agentCard("dispatch", ["ops"]), agentCard("crm", ["sales", "ops"]), agentCard("docs", ["admin"])];
  return { company: { name: "Acme" }, departments, people, agents };
}

describe("buildOrgSphereLayout", () => {
  it("seats every node on the radius for its shell", () => {
    const layout = buildOrgSphereLayout(scenario());
    for (const d of layout.departments) expect(Math.abs(mag(d.position) - R_DEPT)).toBeLessThan(EPS);
    for (const a of layout.agents) expect(Math.abs(mag(a.position) - R_AGENT)).toBeLessThan(EPS);
    for (const p of layout.people) expect(Math.abs(mag(p.position) - R_PEOPLE)).toBeLessThan(EPS);
    expect(layout.company.position).toEqual([0, 0, 0]);
  });

  it("preserves every person and agent (no drops, no dupes)", () => {
    const input = scenario();
    const layout = buildOrgSphereLayout(input);
    expect(layout.people.map((p) => p.id).sort()).toEqual(input.people.map((p) => p.id).sort());
    expect(layout.agents.map((a) => a.key).sort()).toEqual(input.agents.map((a) => a.key).sort());
    expect(layout.departments).toHaveLength(input.departments.length);
  });

  it("keeps each person inside their department's spherical cap", () => {
    const layout = buildOrgSphereLayout(scenario());
    const dirByKey = new Map(layout.departments.map((d) => [d.key, d]));
    for (const p of layout.people) {
      const d = dirByKey.get(p.departmentKey)!;
      expect(angleBetween(p.position, d.dir)).toBeLessThanOrEqual(d.capAngle + EPS);
    }
  });

  it("colors each person with their department's color", () => {
    const layout = buildOrgSphereLayout(scenario());
    const colorByKey = new Map(layout.departments.map((d) => [d.key, d.color]));
    for (const p of layout.people) expect(p.color).toBe(colorByKey.get(p.departmentKey));
  });

  it("seats the department lead nearer the hub than any non-lead in that department", () => {
    const layout = buildOrgSphereLayout(scenario());
    const byDept = new Map<string, { lead: number[]; rest: number[] }>();
    for (const d of layout.departments) byDept.set(d.key, { lead: [], rest: [] });
    for (const p of layout.people) {
      const d = layout.departments.find((x) => x.key === p.departmentKey)!;
      const polar = angleBetween(p.position, d.dir);
      (p.lead ? byDept.get(p.departmentKey)!.lead : byDept.get(p.departmentKey)!.rest).push(polar);
    }
    for (const { lead, rest } of byDept.values()) {
      if (lead.length === 0 || rest.length === 0) continue;
      expect(Math.max(...lead)).toBeLessThanOrEqual(Math.min(...rest) + EPS);
    }
  });

  it("gives a larger department a wider cap than a smaller one", () => {
    const layout = buildOrgSphereLayout(scenario());
    const ops = layout.departments.find((d) => d.key === "ops")!; // 4 seated
    const sales = layout.departments.find((d) => d.key === "sales")!; // 2 seated
    const admin = layout.departments.find((d) => d.key === "admin")!; // 1 seated
    expect(ops.capAngle).toBeGreaterThan(sales.capAngle);
    expect(sales.capAngle).toBeGreaterThan(admin.capAngle);
  });

  it("spreads department directions apart (no two collapse to the same point)", () => {
    const layout = buildOrgSphereLayout(scenario());
    for (const d of layout.departments) expect(Math.abs(mag(d.dir) - 1)).toBeLessThan(EPS);
    for (let i = 0; i < layout.departments.length; i++) {
      for (let j = i + 1; j < layout.departments.length; j++) {
        expect(angleBetween(layout.departments[i].dir, layout.departments[j].dir)).toBeGreaterThan(0.3);
      }
    }
  });

  it("homes each agent on the mid shell near its primary department", () => {
    const layout = buildOrgSphereLayout(scenario());
    const dispatch = layout.agents.find((a) => a.key === "dispatch")!;
    expect(dispatch.homeKey).toBe("ops");
    // crm's primary dept is sales (dept_keys[0]); it still records both as servesKeys.
    const crm = layout.agents.find((a) => a.key === "crm")!;
    expect(crm.homeKey).toBe("sales");
    expect(crm.servesKeys).toEqual(["sales", "ops"]);
  });

  it("is deterministic — identical input yields identical output", () => {
    const input = scenario();
    expect(buildOrgSphereLayout(input)).toEqual(buildOrgSphereLayout(input));
  });

  it("holds the cap and radius invariants at scale (8 depts, 400 people)", () => {
    const departments = Array.from({ length: 8 }, (_, i) =>
      dept(`d${i}`, i, `#${(i * 111111).toString(16).padStart(6, "0").slice(0, 6)}`, 50),
    );
    const people = Array.from({ length: 400 }, (_, i) =>
      person(`p${i}`, `d${i % 8}`, i % 50 === 0 ? "exec" : "ic"),
    );
    const layout = buildOrgSphereLayout({ company: { name: "Big" }, departments, people, agents: [] });
    expect(layout.people).toHaveLength(400);
    const dirByKey = new Map(layout.departments.map((d) => [d.key, d]));
    for (const p of layout.people) {
      expect(Math.abs(mag(p.position) - R_PEOPLE)).toBeLessThan(1e-6);
      const d = dirByKey.get(p.departmentKey)!;
      expect(angleBetween(p.position, d.dir)).toBeLessThanOrEqual(d.capAngle + 1e-6);
    }
  });
});
