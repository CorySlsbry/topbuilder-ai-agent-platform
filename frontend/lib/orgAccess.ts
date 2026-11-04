// Department isolation + sensible partner-access policy for the Org Brain.
//
// The principle (mirrors the backend's department-scoped permissions): an employee's AI sees only
// their own department plus PARTNER departments that legitimately collaborate — never sensitive
// partitions like Finance or HR/People across the org. Leadership (owner/exec) sees everything.
//
// This is the presentation/derivation layer the 3D sphere + demo use; the server is still the
// real enforcement boundary (RLS + per-request scope). Keeping the rules here as data lets both
// the 2D wheel and the 3D sphere explain "who can see what" identically.

export type DeptAccess = {
  departmentKey: string;
  isLeadership: boolean;
  /** Departments this person's AI can pull context from (own + partners, or all for leadership). */
  accessibleDepts: string[];
  /** Departments explicitly walled off (esp. the sensitive ones: finance, hr). */
  isolatedDepts: string[];
  /** Why each isolated dept is blocked — for the UI tooltip. */
  isolationReason: string;
};

// Partner graph — collaboration that makes operational sense. Sensitive departments (finance, hr)
// are intentionally NOT partners with the operational side; only leadership crosses into them.
const PARTNERS: Record<string, string[]> = {
  operations: ["service", "warehouse", "sales"], // field ops coordinate jobs, materials, hand-offs
  service: ["operations", "warehouse"],
  warehouse: ["operations", "service"],
  sales: ["marketing", "operations"], // revenue side + ops hand-off
  marketing: ["sales"],
  finance: [], // sensitive — isolated; only leadership
  hr: [], // sensitive (People) — isolated; only leadership
  admin: ["operations"], // support function, no sensitive access
};

// Departments treated as sensitive partitions (the ones the user called out — e.g. Finance must not
// reach HR and vice-versa). Non-leadership outside these never gets in.
const SENSITIVE = new Set(["finance", "hr"]);

const LEADERSHIP_TIERS = new Set(["owner", "exec"]);

export function computeDeptAccess(
  person: { department_key: string; role_tier: string },
  allDeptKeys: string[],
): DeptAccess {
  const own = person.department_key;
  const isLeadership = LEADERSHIP_TIERS.has(person.role_tier);

  if (isLeadership) {
    return {
      departmentKey: own,
      isLeadership: true,
      accessibleDepts: [...allDeptKeys],
      isolatedDepts: [],
      isolationReason: "Leadership has org-wide visibility.",
    };
  }

  const partners = PARTNERS[own] ?? [];
  const accessible = [own, ...partners.filter((k) => allDeptKeys.includes(k))];
  const accessibleSet = new Set(accessible);
  const isolated = allDeptKeys.filter((k) => !accessibleSet.has(k));

  const sensitiveIsolated = isolated.filter((k) => SENSITIVE.has(k));
  const reason =
    sensitiveIsolated.length > 0
      ? `Department isolation: ${sensitiveIsolated.join(", ")} are sensitive partitions, walled off from ${own}. Other departments are simply outside this role's partner scope.`
      : "These departments are outside this role's partner scope.";

  return {
    departmentKey: own,
    isLeadership: false,
    accessibleDepts: accessible,
    isolatedDepts: isolated,
    isolationReason: reason,
  };
}

// Which AI agents a department's people may use. Mirrors the backend DEPT_AGENTS concept: each
// department gets the agents relevant to its work; sensitive ones (Financial) stay with their dept
// + leadership. Leadership gets all agents.
const DEPT_AGENTS: Record<string, string[]> = {
  operations: ["workforce", "routing", "inventory", "booking"],
  service: ["routing", "booking", "documents"],
  warehouse: ["inventory", "documents"],
  sales: ["booking"],
  marketing: ["booking"],
  finance: ["financial"],
  hr: ["workforce"],
  admin: ["documents"],
};

export type AgentRef = { key: string; label: string };

export function computeAgentAccess(
  person: { department_key: string; role_tier: string },
  allAgents: AgentRef[],
): { allowed: AgentRef[]; locked: AgentRef[] } {
  const isLeadership = LEADERSHIP_TIERS.has(person.role_tier);
  if (isLeadership) return { allowed: [...allAgents], locked: [] };
  const allowedKeys = new Set(DEPT_AGENTS[person.department_key] ?? []);
  const allowed = allAgents.filter((a) => allowedKeys.has(a.key));
  const locked = allAgents.filter((a) => !allowedKeys.has(a.key));
  return { allowed, locked };
}
