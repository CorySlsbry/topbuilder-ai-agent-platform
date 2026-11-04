// Deterministic concentric-shell layout for the 3D Organization Sphere.
//
// Mirrors the 2D radial wheel's hierarchy (company → departments → agents → people) but in 3D:
//   - company at the origin,
//   - departments evenly spread on an inner shell (Fibonacci sphere),
//   - AI agents on a mid shell, fanned around their home department's direction,
//   - people on the outer shell, seated inside their department's spherical "cap" (a sunflower
//     patch) so each department clusters together and radial dept→person edges stay short.
//
// The cap's solid angle scales with the department's share of headcount, so a big department
// claims a wider continent. Pure + deterministic (no RNG, no Date) so the same roster always
// produces the same sphere — this is what makes it unit-testable and preserves spatial memory.

import type { OrgAgentCard, OrgDepartment, OrgPerson } from "@/lib/types";

export type Vec3 = readonly [number, number, number];

export type SphereCompany = { name: string; position: Vec3 };
export type SphereDept = {
  key: string;
  name: string;
  color: string;
  headCount: number;
  /** Unit direction from the origin to this department's center. */
  dir: Vec3;
  position: Vec3;
  /** Half-angle (radians) of the spherical cap this department's people fill. */
  capAngle: number;
};
export type SphereAgent = {
  key: string;
  label: string;
  color: string;
  homeKey: string | null;
  servesKeys: string[];
  position: Vec3;
};
export type SpherePerson = {
  id: string;
  name: string;
  title: string;
  departmentKey: string;
  roleTier: string;
  managerId: string | null;
  color: string;
  lead: boolean;
  position: Vec3;
};
export type OrgSphereLayout = {
  company: SphereCompany;
  departments: SphereDept[];
  agents: SphereAgent[];
  people: SpherePerson[];
  radii: { dept: number; agent: number; people: number };
};

// Shell radii (scene units). Outer >> inner so the hierarchy reads as depth.
export const R_DEPT = 3.4;
export const R_AGENT = 5.2;
export const R_PEOPLE = 8.0;

// Fraction of the full sphere the people-caps consume in aggregate. < 1 leaves gaps between
// departments so they read as distinct "continents" rather than a seamless ball.
const CAP_PACKING = 0.62;
const CAP_MIN = 0.2; // rad — a 1-person dept still gets a visible patch
const CAP_MAX = 1.15; // rad — keep a cap from wrapping past a hemisphere

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5)); // ≈ 2.39996 rad
export const FALLBACK_COLOR = "#5b8cff";

const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const scale = (a: Vec3, s: number): Vec3 => [a[0] * s, a[1] * s, a[2] * s];
const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a: Vec3, b: Vec3): Vec3 => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
const length = (a: Vec3): number => Math.sqrt(dot(a, a));
const normalize = (a: Vec3): Vec3 => {
  const len = length(a) || 1;
  return [a[0] / len, a[1] / len, a[2] / len];
};

/** i-th of n evenly distributed unit directions on a sphere (Fibonacci / golden-spiral). */
function fibonacciDir(i: number, n: number): Vec3 {
  const y = n <= 1 ? 0 : 1 - (2 * i + 1) / n; // pole-to-pole, off the exact poles
  const r = Math.sqrt(Math.max(0, 1 - y * y));
  const theta = GOLDEN_ANGLE * i;
  return [r * Math.cos(theta), y, r * Math.sin(theta)];
}

/** Orthonormal tangent basis {u, v} for a unit direction, so we can offset within its cap. */
function tangentBasis(dir: Vec3): { u: Vec3; v: Vec3 } {
  // Pick a helper axis least parallel to dir to avoid a degenerate cross product.
  const helper: Vec3 = Math.abs(dir[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0];
  const u = normalize(cross(dir, helper));
  const v = cross(dir, u); // already unit (dir ⟂ u, both unit)
  return { u, v };
}

/** A point at `radius`, `polar` radians off `dir`, rotated `azimuth` around it. |result| === radius. */
function pointInCap(
  dir: Vec3,
  basis: { u: Vec3; v: Vec3 },
  polar: number,
  azimuth: number,
  radius: number,
): Vec3 {
  const along = Math.cos(polar);
  const out = Math.sin(polar);
  const tangent = add(scale(basis.u, Math.cos(azimuth)), scale(basis.v, Math.sin(azimuth)));
  return scale(add(scale(dir, along), scale(tangent, out)), radius);
}

function capAngleFor(share: number): number {
  // Solid angle Ω = 2π(1 − cos α); allocate Ω = packing · share · 4π ⇒ cos α = 1 − 2·packing·share.
  const cosA = 1 - 2 * CAP_PACKING * share;
  const alpha = Math.acos(Math.max(-1, Math.min(1, cosA)));
  return Math.max(CAP_MIN, Math.min(CAP_MAX, alpha));
}

/** Leads (owners/execs) seat nearest their department hub. */
const isLead = (roleTier: string): boolean => roleTier === "owner" || roleTier === "exec";

export function buildOrgSphereLayout(input: {
  company: { name: string };
  departments: OrgDepartment[];
  people: OrgPerson[];
  agents: OrgAgentCard[];
}): OrgSphereLayout {
  const orderedDepts = [...input.departments].sort((a, b) => a.sort - b.sort);

  const peopleByDept = new Map<string, OrgPerson[]>();
  for (const p of input.people) {
    const list = peopleByDept.get(p.department_key);
    if (list) list.push(p);
    else peopleByDept.set(p.department_key, [p]);
  }

  // Weight each cap by actual seated headcount (min 1) so empty/tiny depts still get a patch.
  const weightFor = (key: string) => Math.max(peopleByDept.get(key)?.length ?? 0, 1);
  const totalWeight = orderedDepts.reduce((sum, d) => sum + weightFor(d.key), 0) || 1;

  const colorByDept = new Map<string, string>();
  const dirByDept = new Map<string, Vec3>();
  const departments: SphereDept[] = orderedDepts.map((dept, i) => {
    const dir = fibonacciDir(i, orderedDepts.length);
    const capAngle = capAngleFor(weightFor(dept.key) / totalWeight);
    colorByDept.set(dept.key, dept.color || FALLBACK_COLOR);
    dirByDept.set(dept.key, dir);
    return {
      key: dept.key,
      name: dept.name,
      color: dept.color || FALLBACK_COLOR,
      headCount: dept.head_count,
      dir,
      position: scale(dir, R_DEPT),
      capAngle,
    };
  });

  // People: seat each department's members in a sunflower patch across its cap, leads first
  // (smallest radius ⇒ nearest the hub).
  const people: SpherePerson[] = [];
  for (const dept of departments) {
    const members = [...(peopleByDept.get(dept.key) ?? [])].sort((a, b) => {
      const la = isLead(a.role_tier) ? 0 : 1;
      const lb = isLead(b.role_tier) ? 0 : 1;
      return la - lb; // stable: leads keep their relative order, then the rest
    });
    const n = members.length;
    if (n === 0) continue;
    const basis = tangentBasis(dept.dir);
    members.forEach((person, j) => {
      const t = Math.sqrt((j + 0.5) / n); // even area fill of the disc → cap
      const polar = t * dept.capAngle;
      const azimuth = GOLDEN_ANGLE * j;
      people.push({
        id: person.id,
        name: person.full_name,
        title: person.title,
        departmentKey: person.department_key,
        roleTier: person.role_tier,
        managerId: person.manager_id,
        color: colorByDept.get(person.department_key) ?? FALLBACK_COLOR,
        lead: isLead(person.role_tier),
        position: pointInCap(dept.dir, basis, polar, azimuth, R_PEOPLE),
      });
    });
  }

  // Agents: fan around their home department's direction on the mid shell. Homeless/global
  // agents settle on the top pole so they're still reachable.
  const agentsByHome = new Map<string, OrgAgentCard[]>();
  const homeless: OrgAgentCard[] = [];
  for (const a of input.agents) {
    const home = a.dept_keys[0] ?? null;
    if (home && dirByDept.has(home)) {
      const list = agentsByHome.get(home);
      if (list) list.push(a);
      else agentsByHome.set(home, [a]);
    } else {
      homeless.push(a);
    }
  }
  const agents: SphereAgent[] = [];
  for (const dept of departments) {
    const group = agentsByHome.get(dept.key);
    if (!group) continue;
    const basis = tangentBasis(dept.dir);
    group.forEach((agent, k) => {
      const polar = group.length === 1 ? 0 : 0.26;
      const azimuth = group.length === 1 ? 0 : (k / group.length) * Math.PI * 2;
      agents.push({
        key: agent.key,
        label: agent.label,
        color: colorByDept.get(dept.key) ?? FALLBACK_COLOR,
        homeKey: dept.key,
        servesKeys: agent.dept_keys,
        position: pointInCap(dept.dir, basis, polar, azimuth, R_AGENT),
      });
    });
  }
  const poleDir: Vec3 = [0, 1, 0];
  const poleBasis = tangentBasis(poleDir);
  homeless.forEach((agent, k) => {
    const polar = homeless.length === 1 ? 0 : 0.3;
    const azimuth = homeless.length === 1 ? 0 : (k / homeless.length) * Math.PI * 2;
    agents.push({
      key: agent.key,
      label: agent.label,
      color: FALLBACK_COLOR,
      homeKey: null,
      servesKeys: agent.dept_keys,
      position: pointInCap(poleDir, poleBasis, polar, azimuth, R_AGENT),
    });
  });

  return {
    company: { name: input.company.name, position: [0, 0, 0] },
    departments,
    agents,
    people,
    radii: { dept: R_DEPT, agent: R_AGENT, people: R_PEOPLE },
  };
}

/** Angle (radians) between two vectors — used by tests and the scene's cap math. */
export function angleBetween(a: Vec3, b: Vec3): number {
  const cosA = dot(a, b) / ((length(a) || 1) * (length(b) || 1));
  return Math.acos(Math.max(-1, Math.min(1, cosA)));
}
