// Single source of truth for the "connected highlight" set, shared by the 2D wheel and the 3D
// sphere so the two views can never drift. A person highlights itself + manager + direct reports;
// an agent highlights the departments it serves; a department highlights its people + agents.

import type { OrgOverview } from "@/lib/types";

export type OrgFocus = { people: Set<string>; depts: Set<string>; agents: Set<string> } | null;

export type OrgSelectionRef = {
  personId?: string | null;
  agentKey?: string | null;
  deptKey?: string | null;
};

export function computeFocus(data: OrgOverview, sel: OrgSelectionRef): OrgFocus {
  if (sel.personId) {
    const p = data.people.find((x) => x.id === sel.personId);
    if (!p) return null;
    const people = new Set([p.id]);
    if (p.manager_id) people.add(p.manager_id);
    for (const o of data.people) if (o.manager_id === p.id) people.add(o.id);
    return { people, depts: new Set([p.department_key]), agents: new Set<string>() };
  }
  if (sel.agentKey) {
    const a = data.agents.find((x) => x.key === sel.agentKey);
    if (!a) return null;
    return { people: new Set<string>(), depts: new Set(a.dept_keys), agents: new Set([a.key]) };
  }
  if (sel.deptKey) {
    const people = new Set(data.people.filter((x) => x.department_key === sel.deptKey).map((x) => x.id));
    const agents = new Set(data.agents.filter((x) => x.dept_keys.includes(sel.deptKey!)).map((x) => x.key));
    return { people, depts: new Set([sel.deptKey]), agents };
  }
  return null;
}
