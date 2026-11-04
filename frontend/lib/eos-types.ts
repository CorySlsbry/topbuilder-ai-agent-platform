// EOS communication-hub types (Issues + Business Plan) — mirrors backend/app/org/eos.py exactly.
// Owned by the IssuesView / BusinessPlanView build. The matching API helpers are added to lib/api.ts
// (see the build's shared_edits); these types stand alone so the views compile against them.

export type IssuePriority = 1 | 2 | 3;
export type IssueStatus = "open" | "closed";

export type Issue = {
  id: string;
  title: string;
  owner: string;
  /** department key (mirrors permissions.DEPARTMENTS); "" = company-wide. */
  department: string;
  priority: number;
  status: IssueStatus;
  created: string; // YYYY-MM-DD
  resolved: string | null; // YYYY-MM-DD when closed
};

export type IssueSummary = {
  total: number;
  open: number;
  closed: number;
  /** open issues by priority — keys "1" | "2" | "3". */
  open_by_priority: Record<string, number>;
};

export type IssuesPayload = {
  issues: Issue[];
  summary: IssueSummary;
};

export type IssueCreate = {
  title: string;
  owner?: string;
  department?: string;
  priority?: number;
};

// ---------------- Business Plan ----------------
export type AnnualGoal = {
  key: string;
  label: string;
  unit: "usd" | "percent" | "count" | "ratio";
  /** usd goals are emitted in dollars at the API boundary. */
  target: number;
  actual: number | null;
  higher_is_better: boolean;
  /** higher_is_better ? actual>=target : actual<=target; null when actual unmeasured. */
  on_track: boolean | null;
  /** actual ÷ target × 100; null on a 0/absent denominator. */
  attainment_pct: number | null;
};

export type BudgetLineKind = "revenue" | "cogs" | "expense";

export type BudgetLine = {
  key: string;
  label: string;
  kind: BudgetLineKind;
  budget: number; // dollars
  actual: number; // dollars
  variance: number; // dollars (actual − budget)
  variance_pct: number | null;
  /** true = the variance is good for the business (revenue over / cost under budget). */
  favorable: boolean;
};

export type BudgetBlock = { budget: number; actual: number; variance: number };
export type NetIncomeBlock = BudgetBlock & { favorable: boolean };

export type BudgetToActual = {
  lines: BudgetLine[];
  totals: {
    revenue: BudgetBlock;
    cogs: BudgetBlock;
    expense: BudgetBlock;
    net_income: NetIncomeBlock;
  };
};

export type TrailingPoint = {
  month: string; // YYYY-MM
  revenue: number; // dollars
  net_income: number; // dollars
  net_margin_pct: number | null;
};

export type Trailing12 = {
  points: TrailingPoint[];
  totals: { revenue: number; net_income: number; net_margin_pct: number | null; months: number };
};

export type BusinessPlan = {
  company: string;
  fiscal_year: number;
  period_label: string;
  annual_goals: AnnualGoal[];
  budget_to_actual: BudgetToActual;
  trailing_12: Trailing12;
};
