export type AgentName =
  | "workforce" | "financial" | "inventory" | "booking" | "routing" | "documents" | "pricebook";

// ---------------- Workforce ----------------
export type UnderstaffingRisk = {
  week_start: string;
  week_offset: number;
  trade_type: string;
  gap_count: number;
  gap_hours: number;
  available_hours: number;
  projected_required_hours: number;
  economic_impact_usd: number;
  confidence: number;
  reasoning: string;
};

export type OvertimeWeek = {
  week_offset: number;
  week_start: string;
  scheduled_hours: number;
  overtime_hours: number;
  confidence: number;
};

export type OvertimeRisk = {
  technician_id: string;
  technician_name: string;
  trade: string;
  projected_overtime_hours: number;
  economic_impact_usd: number;
  recent_overtime_hours: number;
  weeks: OvertimeWeek[];
  mitigation_strategy: string;
  mitigation_candidates: string[];
  confidence: number;
  reasoning: string;
};

export type TradeUtilization = {
  trade: string;
  week_offset: number;
  available_hours: number;
  projected_required_hours: number;
  utilization: number;
};

export type WorkforceRunResult = {
  run_id: string | null;
  agent: "workforce";
  analysis_timestamp: string;
  as_of: string;
  horizon_days: number;
  understaffing_risks: UnderstaffingRisk[];
  overtime_risks: OvertimeRisk[];
  utilization: TradeUtilization[];
  totals: {
    weeks_short: number;
    total_understaffing_impact_usd: number;
    technicians_in_overtime: number;
    total_overtime_premium_usd: number;
  };
  reasoning_logs: string;
  inputs_hash: string;
};

// ---------------- Financial ----------------
export type JobProfitability = {
  job_id: string;
  name: string;
  customer_segment: string;
  earned_revenue: number;
  actual_cost: number;
  margin_to_date: number;
  budget_margin: number;
  profitability_index: number;
  billing_position: number;
  confidence: number;
  reasoning: string;
};

export type CashFlowBucket = {
  horizon_days: number;
  inflows: number;
  outflows: number;
  projected_cash: number;
  confidence: number;
};

export type LeakageWarning = {
  job_id: string;
  name: string;
  kind: string;
  severity_usd: number;
  detail: string;
  confidence: number;
};

export type SegmentMargin = {
  segment: string;
  earned_revenue: number;
  cost: number;
  margin: number;
};

export type FinancialRunResult = {
  run_id: string | null;
  agent: "financial";
  analysis_timestamp: string;
  as_of: string;
  starting_cash: number;
  wip_profitability: JobProfitability[];
  cash_flow_projection: CashFlowBucket[];
  leakage_warnings: LeakageWarning[];
  segment_margins: SegmentMargin[];
  totals: {
    projects_at_risk: number;
    total_leakage_usd: number;
    cash_30_day: number;
    cash_90_day: number;
    lowest_margin_segment: string | null;
  };
  reasoning_logs: string;
  inputs_hash: string;
};

// ---------------- Inventory ----------------
export type Reorder = {
  sku: string;
  name: string;
  on_hand: number;
  avg_daily_usage: number;
  lead_time_days: number;
  dynamic_reorder_point: number;
  days_to_stockout: number | null;
  recommended_order_qty: number;
  stockout_exposure_usd: number;
  margin_class: string;
  confidence: number;
  reasoning: string;
};

export type Shrinkage = {
  technician_id: string;
  sku: string;
  name: string;
  expected_qty: number;
  counted_qty: number;
  variance: number;
  shrinkage_value_usd: number;
  confidence: number;
  reasoning: string;
};

export type Unbilled = {
  job_id: string;
  sku: string;
  name: string;
  qty_used: number;
  unbilled_value_usd: number;
  reasoning: string;
};

export type Arbitrage = {
  sku: string;
  name: string;
  current_unit_cost: number;
  best_vendor: string;
  best_unit_price: number;
  annual_savings_usd: number;
  reasoning: string;
};

export type InventoryRunResult = {
  run_id: string | null;
  agent: "inventory";
  analysis_timestamp: string;
  as_of: string;
  critical_reorders: Reorder[];
  shrinkage_alerts: Shrinkage[];
  unbilled_materials: Unbilled[];
  vendor_arbitrage: Arbitrage[];
  totals: {
    reorders_count: number;
    total_stockout_exposure_usd: number;
    total_shrinkage_usd: number;
    total_unbilled_usd: number;
    total_arbitrage_annual_usd: number;
  };
  reasoning_logs: string;
  inputs_hash: string;
};

// ---------------- Booking (24/7) ----------------
export type ProposedBooking = {
  intake_id: string;
  caller_name: string | null;
  trade: string;
  job_type: string | null;
  urgency: string;
  after_hours: boolean;
  proposed_date: string;
  estimated_value_usd: number;
  confidence: number;
  status: string;
  reasoning: string;
};

export type UnbookedIntake = {
  intake_id: string;
  trade: string;
  reason: string;
};

export type BookingRunResult = {
  run_id: string | null;
  agent: "booking";
  analysis_timestamp: string;
  as_of: string;
  proposed_bookings: ProposedBooking[];
  unbooked: UnbookedIntake[];
  totals: {
    intakes_received: number;
    qualified: number;
    proposed_bookings: number;
    screened_out: number;
    after_hours_captured: number;
    recovered_revenue_usd: number;
    after_hours_recovered_usd: number;
  };
  reasoning_logs: string;
  inputs_hash: string;
};

// ---------------- Routing / Dispatch ----------------
export type RoutingSuggestion = {
  job_id: string;
  customer_name: string;
  trade: string;
  required_skill: string;
  tech_id: string;
  tech_name: string;
  sequence: number;
  drive_minutes: number;
  arrival: string;
  confidence: number;
  reasoning: string;
};

export type UnassignedJob = { job_id: string; trade: string; reason: string };

export type RoutingRunResult = {
  run_id: string | null;
  agent: "routing";
  analysis_timestamp: string;
  as_of: string;
  suggestions: RoutingSuggestion[];
  unassigned: UnassignedJob[];
  totals: {
    jobs: number;
    assigned: number;
    unassigned: number;
    techs_used: number;
    drive_minutes_optimized: number;
    drive_minutes_baseline: number;
    drive_minutes_saved: number;
    hours_saved: number;
  };
  reasoning_logs: string;
  inputs_hash: string;
};

// ---------------- Documents ----------------
export type DocumentFiling = {
  doc_id: string;
  filename: string;
  doc_type: string;
  customer_ref: string;
  customer_name: string;
  department: string;
  st_folder: string;
  amount_usd: number | null;
  expiry_in_days: number | null;
  action: "file" | "expiring" | "needs_signature";
  confidence: number;
  reasoning: string;
};

export type DocNeedsHuman = { doc_id: string; filename: string; doc_type: string; reason: string };

export type DocumentsRunResult = {
  run_id: string | null;
  agent: "documents";
  analysis_timestamp: string;
  as_of: string;
  filings: DocumentFiling[];
  needs_human: DocNeedsHuman[];
  totals: {
    documents_processed: number;
    auto_filed: number;
    needs_signature: number;
    needs_human: number;
    expiring_soon: number;
    extracted_value_usd: number;
  };
  reasoning_logs: string;
  inputs_hash: string;
};

// ---------------- Operating layer (front-desk) ----------------
export type Communication = {
  id: string;
  channel: "call" | "sms" | "email" | "voicemail" | "web";
  direction: "inbound" | "outbound";
  contact_name: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  subject: string | null;
  body: string | null;
  status: string;
  occurred_at: string;
  agent_handled: boolean;
};

export type Task = {
  id: string;
  title: string;
  detail: string | null;
  department: string;
  status: "open" | "in_progress" | "done";
  priority: number;
  source_agent: string | null;
  related_ref: string | null;
  assignee_role: string | null;
  due_at: string | null;
};

export type AgentMode = "off" | "hitl" | "auto";
export type AgentPolicy = { agent: string; mode: AgentMode; updated_at: string | null };

// ---------------- Organization (org brain) ----------------
export type OrgDepartment = {
  id: string;
  key: string;
  name: string;
  color: string;
  sort: number;
  head_count: number;
};

export type OrgPerson = {
  id: string;
  full_name: string;
  title: string;
  department_key: string;
  role_tier: string;
  manager_id: string | null;
};

export type OrgAgentCard = {
  key: string;
  label: string;
  dept_keys: string[];
  description: string;
};

export type OrgOverview = {
  company: { name: string; employee_count: number; provider: string };
  departments: OrgDepartment[];
  people: OrgPerson[];
  agents: OrgAgentCard[];
  caller_access: { department: string | null; allowed_agents: string[] | null };
};

export type OrgPersonRef = { id: string; full_name: string; title: string };

export type OrgPersonProfile = {
  person: {
    id: string;
    full_name: string;
    title: string;
    department_key: string;
    department_name: string;
    color: string;
    role_tier: string;
    email: string | null;
    ai_context: string;
  };
  manager: OrgPersonRef | null;
  direct_reports: OrgPersonRef[];
  ai_access: {
    agents: string[];
    sections: string[];
    not_accessible: string[];
    /** Per-agent on/off + whether it's the department default or an explicit override. */
    agent_states?: AgentState[];
    /** True when the calling principal may grant/revoke this person's agents. */
    can_manage?: boolean;
  };
};

export type AgentState = { agent: string; enabled: boolean; default: boolean; overridden: boolean };
export type AgentOverrideMode = "grant" | "revoke" | "default";

// ---------------- Executive KPIs (org-wide rollup from persisted latest runs) ----------------
export type OrgKpiUnit = "usd" | "minutes_per_day" | "count" | "hours";

export type OrgKpi = {
  key: string;
  label: string;
  /** null = that agent has no persisted latest run yet. */
  value: number | null;
  unit: OrgKpiUnit;
  agent: string | null;
  detail: string;
};

export type OrgKpis = {
  kpis: OrgKpi[];
  value_by_agent: { agent: string; label: string; usd: number }[];
  headcount_by_department: { key: string; name: string; color: string; head_count: number }[];
  agents_active: number;
  runs_present: number;
  employee_count: number;
  departments_covered: number;
};

// ---------------- Executive KPI timeseries (history — the "go backwards" view) ----------------
export type KpiSeriesPoint = { date: string; value: number | null };

export type KpiSeries = {
  key: string;
  label: string;
  agent: string;
  /** The metric's home department (drives color + the department panel it lives in). */
  department: string | null;
  color: string | null;
  unit: OrgKpiUnit;
  points: KpiSeriesPoint[];
};

export type OrgKpiTimeseries = {
  dates: string[];
  series: KpiSeries[];
};

// ---------------- Department Scorecard (the Bloom Growth L10 replacement) ----------------
// Auto-computed scorecard: every figure is produced by the pure deterministic engine (ADR-0003).
// The contract mirrors backend/app/org/scorecard.py exactly (see docs/ALEX_SCORECARD_SPEC.md).

/** Display units the scorecard engine emits. `usd` is dollars at the API boundary (cents internally). */
export type ScorecardUnit =
  | "usd"
  | "percent"
  | "ratio"
  | "count"
  | "hours"
  | "minutes_per_day"
  | "bool";

/** One weekly history point. `value` is in display units (usd dollars, etc.); null = no data that week. */
export type SeriesPoint = { date: string; value: number | null };

/** The full catalog entry for a KPI — the single source of truth the engine + FE selector share. */
export type KpiDef = {
  key: string;
  label: string;
  department: string;
  unit: ScorecardUnit;
  calculated: boolean;
  goal: number | null;
  higher_is_better: boolean;
  description: string;
};

export type KpiValue = {
  key: string;
  /** null when a denominator is 0/absent (calculated KPIs) or the source has no figure. */
  value: number | null;
  goal: number | null;
  /** higher_is_better ? value>=goal : value<=goal; null when no goal or no value. */
  on_goal: boolean | null;
  /** Percent change vs the first present series point; null with <2 points or a zero base. */
  delta_pct: number | null;
  /** Dept-level weekly history (the trend Bloom can't show). */
  series: SeriesPoint[];
};

/** A rep / tech / CSR row for the per-entity side-by-side panel. */
export type EntityRow = {
  entity_id: string;
  entity_name: string;
  /** "sales_rep" | "technician" | "csr" */
  role: string;
  /** kpi_key -> current value (null when not applicable / no denominator). */
  values: Record<string, number | null>;
  /** Small trend for the department's primary metric. */
  headline_series: SeriesPoint[];
};

export type DepartmentScorecard = {
  key: string;
  label: string;
  /** "ServiceTitan" | "QuickBooks" */
  source: string;
  kpis: KpiValue[];
  /** null for finance (company-level, no per-entity breakdown). */
  entity_role: string | null;
  /** Which catalog keys render per-entity in the side-by-side panel. */
  entity_kpi_keys: string[];
  entities: EntityRow[];
};

export type Scorecard = {
  period_weeks: number;
  departments: DepartmentScorecard[];
  /** The full catalog so the selector knows every KPI (incl. ones not in `departments`). */
  catalog: KpiDef[];
};

// ---------------- KPI Trends (rolling-year actuals + a deterministic seasonal forecast band) ------
// Mirrors GET /v1/org/scorecard/trends (backend/app/api/routes_org.py::scorecard_trends). Money
// fields are already in display dollars (ADR-0003). Every point is deterministic — the forward band
// is a damped trend + year-over-year seasonal overlay, never an LLM guess.

/** One trend point. `projected` distinguishes a rolling-year ACTUAL from the forward forecast band. */
export type TrendPoint = { date: string; value: number | null; projected: boolean };

/** One KPI's trend: catalog metadata + the current snapshot + weekly & monthly point series. */
export type TrendKpi = {
  key: string;
  label: string;
  unit: ScorecardUnit;
  calculated: boolean;
  goal: number | null;
  higher_is_better: boolean;
  description: string;
  /** Latest actual value (display units), or null when the source has no figure. */
  current: number | null;
  /** higher_is_better ? current>=goal : current<=goal; null when no goal or no value. */
  on_goal: boolean | null;
  /** Percent change vs the first present actual; null with <2 points or a zero base. */
  delta_pct: number | null;
  /** Rolling-year weekly actuals THEN the forward band (projected=true), in chronological order. */
  weekly: TrendPoint[];
  /** Month rollup of weekly + forecast (sum flow / last snapshot / mean rate per the KPI). */
  monthly: TrendPoint[];
  /** The date of the first projected point (the "today"/forecast-start divider); null with no band. */
  forecast_from: string | null;
};

export type TrendDepartment = {
  key: string;
  label: string;
  /** "ServiceTitan" | "QuickBooks" */
  source: string;
  kpis: TrendKpi[];
};

export type ScorecardTrends = {
  history_weeks: number;
  forecast_weeks: number;
  departments: TrendDepartment[];
  /** The full catalog so the selector knows every KPI (incl. ones not currently returned). */
  catalog: KpiDef[];
};

// ---------------- Access matrix (who can see what — drives the View-As simulation) ----------------
export type AccessMatrix = {
  departments: { key: string; name: string; color: string; sort: number }[];
  dept_agents: Record<string, string[]>;
  /** null = all sections (leadership). A department missing from the map fails CLOSED. */
  dept_sections: Record<string, string[] | null>;
  agents: OrgAgentCard[];
  all_sections: string[];
};

/** Presentational scope an unrestricted operator can adopt to see exactly what an employee sees. */
export type SimulatedView = {
  personId: string;
  name: string;
  title: string;
  department: string;
  /** null = all sections (leadership); [] = fail-closed nothing. */
  sections: string[] | null;
  /** null = all agents (leadership); [] = fail-closed nothing. */
  agents: string[] | null;
};

export type AgentResult =
  | WorkforceRunResult
  | FinancialRunResult
  | InventoryRunResult
  | BookingRunResult
  | RoutingRunResult
  | DocumentsRunResult;

// ---------------- A/R Collections ----------------
// Mirrors backend/app/agents/collections/schemas.py (CollectionsRunResult). Money fields are USD
// dollars at the API boundary (cents internally, per ADR-0003).
export type CollectionsBucket = "current" | "1-30" | "31-60" | "61-90" | "91-120" | "121+";

export type WorklistInvoice = {
  invoice_id: string;
  doc_number: string | null;
  balance_usd: number;
  days_overdue: number;
  bucket: string;
};

export type DunningDrafts = {
  step: number;
  channel: string;
  email_subject: string | null;
  email_body: string | null;
  sms_body: string | null;
  call_script: string | null;
};

export type WorklistCustomer = {
  customer_id: string;
  customer_name: string;
  customer_segment: string;
  balance_usd: number;
  oldest_days_overdue: number;
  bucket: string;
  status: string;
  owner: string;
  next_action: string;
  dunning_step: number;
  dunning_channel: string;
  promise_date: string | null;
  promise_amount_usd: number | null;
  bucket_balances_usd: Record<string, number>;
  invoices: WorklistInvoice[];
  drafts: DunningDrafts;
};

export type CollectionsTotals = {
  customers: number;
  open_balance_usd: number;
  overdue_balance_usd: number;
  current_balance_usd: number;
  pct_current: number;
  pct_over_30: number;
  bucket_balances_usd: Record<string, number>;
  at_risk_balance_usd: number;
  customers_needing_action: number;
};

export type CollectionsRunResult = {
  run_id: string | null;
  agent: "collections";
  source_system: string;
  analysis_timestamp: string;
  as_of: string;
  worklist: WorklistCustomer[];
  totals: CollectionsTotals;
  reasoning_logs: string;
  inputs_hash: string;
};

// ---------------- Pricebook (cost-driven re-pricing under the sold-hour model) ----------------
// Mirrors backend/app/agents/pricebook/schemas.py (PricebookRunResult). Money fields are USD dollars
// at the API boundary (cents internally, per ADR-0003).
export type MaterialLineChange = {
  sku: string;
  qty: number;
  old_unit_cost_usd: number;
  new_unit_cost_usd: number;
  old_line_cost_usd: number;
  new_line_cost_usd: number;
  vendor: string | null;
};

export type PricebookItemChange = {
  code: string;
  name: string;
  category: string;
  sold_hours: number;
  sold_hour_rate_usd: number;
  markup_pct: number;
  labor_cost_usd: number;
  old_materials_cost_usd: number;
  new_materials_cost_usd: number;
  materials_delta_usd: number;
  old_price_usd: number;
  new_price_usd: number;
  price_delta_usd: number;
  price_delta_pct: number;
  old_margin_usd: number;
  new_margin_usd: number;
  margin_delta_usd: number;
  changed_skus: string[];
  beyond_tolerance: boolean;
  lines: MaterialLineChange[];
};

export type PricebookTotals = {
  items: number;
  items_affected: number;
  items_flagged: number;
  total_price_delta_usd: number;
  distinct_skus: number;
  skus_updated: number;
  vendor_coverage_pct: number;
  avg_markup_pct: number;
};

export type PricebookRunResult = {
  run_id: string | null;
  agent: "pricebook";
  source_system: string;
  analysis_timestamp: string;
  as_of: string;
  tolerance_pct: number;
  changes: PricebookItemChange[];
  totals: PricebookTotals;
  reasoning_logs: string;
  inputs_hash: string;
};

// ---------------- Capacity / Overtime (Workforce capacity engine) ----------------
export type TechDuration = {
  technician_id: string;
  job_type: string;
  trade: string;
  estimate_hours: number;
  rolling_hours: number;
  baseline_hours: number;
  sample_size: number;
  confidence: number;
  efficiency_delta_hours: number; // estimate - baseline; negative => faster than baseline
  pace: "faster" | "slower" | "on baseline";
};

export type TechWeekProjection = {
  technician_id: string;
  trade: string;
  job_count: number;
  projected_hours: number;
  contracted_hours: number;
  overtime_hours: number;
  confidence: number;
  redistribute_to: string[];
  reasoning: string;
};

export type CapacityRunResult = {
  run_id: string | null;
  agent: "capacity";
  source_system: string;
  analysis_timestamp: string;
  as_of: string;
  durations: TechDuration[];
  projections: TechWeekProjection[];
  totals: {
    technicians: number;
    duration_pairs: number;
    techs_over_capacity: number;
    total_overtime_hours: number;
  };
  reasoning_logs: string;
  inputs_hash: string;
};

// ---------------- Dispatch triage (P1/P2/P3 board) ----------------
export type TechRankOut = {
  tech_id: string;
  tech_name: string;
  drive_minutes: number;
  avg_ticket: number; // dollars
  conversion_pct: number;
  revenue_score: number; // 0..100
  score: number; // 0..100
  reason: string;
};

export type TriagedJob = {
  job_id: string;
  customer_name: string;
  trade: string;
  required_skill: string;
  job_type: string;
  priority: number; // 1=P1, 2=P2, 3=P3
  priority_label: string;
  severity_source: string;
  revenue: number; // dollars
  recommended_tech_id: string | null;
  recommended_tech_name: string | null;
  candidates: TechRankOut[];
  assignable: boolean;
  reason: string;
};

export type BoardDay = {
  day: string; // ISO date
  capacity_minutes: number;
  booked_minutes: number;
  free_minutes: number;
  over_capacity_minutes: number;
  utilization_pct: number;
  job_count: number;
  unavailable_tech_ids: string[];
};

export type TriageRunResult = {
  run_id: string | null;
  agent: "routing";
  kind: "triage";
  source_system: string;
  analysis_timestamp: string;
  as_of: string;
  triaged: TriagedJob[];
  board: BoardDay[];
  unassigned_queue: string[];
  totals: { jobs: number; p1: number; p2: number; p3: number; assignable: number; needs_human: number };
  reasoning_logs: string;
  inputs_hash: string;
};
