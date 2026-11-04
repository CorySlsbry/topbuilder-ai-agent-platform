"""EOS "communication hub" engine — the sticky Bloom Growth value BEYOND the scorecard.

Bloom Growth's L10 keeps four things stuck to it: the scorecard (we have it — ``scorecard.py``),
the weekly **to-dos** (we have a tasks worklist), the **Issues list** (the L10 IDS list), and the
**Business Plan** (annual goals + budget-to-actual + a trailing-12 P&L trend). This module is the
PURE, deterministic engine for the last two — issues + business plan — so they round out the
communication hub alongside the org chart + tasks.

ADR 0003 end-to-end: every figure here is produced by tested deterministic code; the LLM never
computes one. Money is carried internally as integer **cents** (the raw bundle) and emitted as
**dollars** at this engine's boundary (the serialized JSON), exactly like ``scorecard.py``. No DB,
no IO — the raw bundle is assembled separately in ``eos_data.py`` (fixture, or QBO P&L when live per
``docs/QBO_DATA_MAP.md``).

Issues are an L10 IDS (Identify-Discuss-Solve) list: ``open`` until resolved, owned by a person,
scoped to a department, prioritized 1 (highest) .. 3. ``apply_issue_create`` / ``apply_issue_resolve``
are pure list transforms (the route persists the result in a tenant-scoped overlay over the seed).
"""
from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------------------------
# Issues (the L10 IDS list)
# --------------------------------------------------------------------------------------------

ISSUE_PRIORITIES: tuple[int, ...] = (1, 2, 3)  # 1 = highest, 3 = lowest
ISSUE_STATUSES: tuple[str, ...] = ("open", "closed")
_MAX_TITLE_LEN = 200


@dataclass(frozen=True)
class Issue:
    """One L10 issue. ``priority`` 1 (highest)..3; ``status`` open|closed; ``created`` is an ISO
    date string; ``resolved`` is the ISO date it was closed (None while open)."""

    id: str
    title: str
    owner: str  # the person responsible for driving it to resolution
    department: str  # department key (mirrors permissions.DEPARTMENTS); "" = company-wide
    priority: int
    status: str  # "open" | "closed"
    created: str  # YYYY-MM-DD
    resolved: str | None = None  # YYYY-MM-DD when closed


def normalize_priority(priority: object) -> int:
    """Coerce a priority to a valid 1..3 (clamped). Non-numeric defaults to 2 (medium)."""
    try:
        p = int(priority)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 2
    return min(max(p, ISSUE_PRIORITIES[0]), ISSUE_PRIORITIES[-1])


def validate_issue_title(title: str) -> str:
    """A non-empty, length-capped title. Raises ValueError on an empty/blank title."""
    cleaned = (title or "").strip()
    if not cleaned:
        raise ValueError("issue title is required")
    return cleaned[:_MAX_TITLE_LEN]


def make_issue(
    *,
    issue_id: str,
    title: str,
    owner: str,
    department: str,
    priority: object,
    created: str,
) -> Issue:
    """Build a validated, OPEN issue (the create transform's core). Pure."""
    return Issue(
        id=issue_id,
        title=validate_issue_title(title),
        owner=(owner or "").strip() or "Unassigned",
        department=(department or "").strip(),
        priority=normalize_priority(priority),
        status="open",
        created=created,
        resolved=None,
    )


def apply_issue_create(issues: list[Issue], issue: Issue) -> list[Issue]:
    """Return a NEW list with ``issue`` prepended (newest first). Pure — never mutates input."""
    return [issue, *issues]


def apply_issue_resolve(issues: list[Issue], issue_id: str, *, resolved_on: str) -> list[Issue]:
    """Return a NEW list with the matching open issue closed on ``resolved_on``. Pure.

    Resolving an already-closed or unknown id is a no-op (idempotent), so a double-tap from the UI
    can never error."""
    out: list[Issue] = []
    for it in issues:
        if it.id == issue_id and it.status == "open":
            out.append(Issue(**{**it.__dict__, "status": "closed", "resolved": resolved_on}))
        else:
            out.append(it)
    return out


def sort_issues(issues: list[Issue]) -> list[Issue]:
    """Display order: OPEN before closed, then priority ascending (1 first), then newest created."""
    return sorted(
        issues,
        key=lambda i: (i.status != "open", i.priority, _neg_date(i.created)),
    )


def _neg_date(iso: str) -> str:
    """Sort key that puts a LATER date first under an ascending sort (lexical inverse of the ISO)."""
    # YYYY-MM-DD is lexically sortable; invert each digit so descending becomes ascending.
    return "".join(str(9 - int(c)) if c.isdigit() else c for c in (iso or ""))


def issue_summary(issues: list[Issue]) -> dict:
    """Counts for the L10 header chips: total / open / closed / open-by-priority."""
    open_issues = [i for i in issues if i.status == "open"]
    by_priority = {p: sum(1 for i in open_issues if i.priority == p) for p in ISSUE_PRIORITIES}
    return {
        "total": len(issues),
        "open": len(open_issues),
        "closed": sum(1 for i in issues if i.status == "closed"),
        "open_by_priority": {str(p): by_priority[p] for p in ISSUE_PRIORITIES},
    }


def issue_to_json(issue: Issue) -> dict:
    return {
        "id": issue.id,
        "title": issue.title,
        "owner": issue.owner,
        "department": issue.department,
        "priority": issue.priority,
        "status": issue.status,
        "created": issue.created,
        "resolved": issue.resolved,
    }


def issues_to_json(issues: list[Issue]) -> dict:
    """The /v1/org/issues payload: a sorted list + the header summary."""
    ordered = sort_issues(issues)
    return {
        "issues": [issue_to_json(i) for i in ordered],
        "summary": issue_summary(issues),
    }


# --------------------------------------------------------------------------------------------
# Business Plan (annual goals + budget-to-actual + trailing-12)
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AnnualGoal:
    """One annual company goal (the V/TO "1-Year Plan" rocks). ``target``/``actual`` are usd CENTS
    when ``unit == 'usd'``; otherwise their natural unit. ``actual`` may be None (not-yet-measured)."""

    key: str
    label: str
    unit: str  # "usd" | "percent" | "count" | "ratio"
    target: float | int
    actual: float | int | None
    higher_is_better: bool


@dataclass(frozen=True)
class BudgetLine:
    """One budget-to-actual P&L line for a single month. Money in integer CENTS.

    ``kind`` ∈ {"revenue", "cogs", "expense"} so the engine can derive net income deterministically
    (revenue − cogs − expense), and so the UI can color a variance the right direction (an OVER on a
    revenue line is good; an OVER on an expense line is bad)."""

    key: str
    label: str
    kind: str  # "revenue" | "cogs" | "expense"
    budget_cents: int
    actual_cents: int


@dataclass(frozen=True)
class TrailingPoint:
    """One trailing-12 monthly P&L point. Money in integer CENTS."""

    month: str  # YYYY-MM
    revenue_cents: int
    net_income_cents: int


@dataclass(frozen=True)
class BusinessPlan:
    company: str
    fiscal_year: int
    period_label: str  # e.g. "June 2026" — the budget-to-actual month
    annual_goals: list[AnnualGoal]
    budget_lines: list[BudgetLine]
    trailing_12: list[TrailingPoint]


_REVENUE_KIND = "revenue"


def _cents_to_dollars(cents: float | int) -> float:
    return round(float(cents) / 100, 2)


def goal_on_track(goal: AnnualGoal) -> bool | None:
    """higher_is_better ? actual>=target : actual<=target. None when actual is not yet measured."""
    if goal.actual is None:
        return None
    return goal.actual >= goal.target if goal.higher_is_better else goal.actual <= goal.target


def goal_attainment_pct(goal: AnnualGoal) -> float | None:
    """Percent of the annual goal reached, DIRECTION-AWARE. None on a 0/absent denominator.

    For a higher-is-better goal (revenue, jobs) this is actual÷target×100. For a lower-is-better goal
    (a cost cap, DSO, overtime budget) raw actual÷target inverts the meaning — hitting 50% of a cost
    target would read as "50% attained" when you are actually 2× UNDER the cap (great). So for those we
    return target÷actual×100, so 100% means "exactly at the cap" and >100% means "beating it" in BOTH
    directions. Capped at 999% to keep a near-zero denominator from producing a nonsense bar.
    """
    if goal.actual is None or not goal.target:
        return None
    if goal.higher_is_better:
        return round(float(goal.actual) / float(goal.target) * 100, 2)
    if not goal.actual:  # at/under a cost cap with zero actual — fully attained
        return 999.0
    return round(min(float(goal.target) / float(goal.actual) * 100, 999.0), 2)


def line_variance_cents(line: BudgetLine) -> int:
    """actual − budget, in CENTS (signed). Positive = actual exceeded budget."""
    return line.actual_cents - line.budget_cents


def line_variance_pct(line: BudgetLine) -> float | None:
    """(actual − budget) ÷ budget × 100. None when the budget is 0 (no meaningful base)."""
    if not line.budget_cents:
        return None
    return round(line_variance_cents(line) / line.budget_cents * 100, 2)


def line_favorable(line: BudgetLine) -> bool:
    """Is this variance GOOD for the business?  Revenue over budget = favorable; an
    expense/COGS line over budget = unfavorable. A zero variance is treated as favorable
    (on-budget is fine)."""
    variance = line_variance_cents(line)
    if line.kind == _REVENUE_KIND:
        return variance >= 0
    return variance <= 0


def _sum(lines: list[BudgetLine], kind: str, *, field: str) -> int:
    return sum(getattr(line, field) for line in lines if line.kind == kind)


def net_income_cents(lines: list[BudgetLine], *, field: str) -> int:
    """Net income (CENTS) for either the ``budget_cents`` or ``actual_cents`` field across the lines:
    revenue − cogs − expense."""
    return (
        _sum(lines, "revenue", field=field)
        - _sum(lines, "cogs", field=field)
        - _sum(lines, "expense", field=field)
    )


def budget_to_actual_totals(lines: list[BudgetLine]) -> dict:
    """Budget/actual/variance totals (in DOLLARS) for revenue, cogs, expense, and derived net income.

    Net income is derived deterministically from the lines (revenue − cogs − expense), never stored
    — so a wrong line can't desync the bottom line (ADR 0003)."""
    budget_net = net_income_cents(lines, field="budget_cents")
    actual_net = net_income_cents(lines, field="actual_cents")

    def block(kind: str) -> dict:
        b = _sum(lines, kind, field="budget_cents")
        a = _sum(lines, kind, field="actual_cents")
        return {
            "budget": _cents_to_dollars(b),
            "actual": _cents_to_dollars(a),
            "variance": _cents_to_dollars(a - b),
        }

    return {
        "revenue": block("revenue"),
        "cogs": block("cogs"),
        "expense": block("expense"),
        "net_income": {
            "budget": _cents_to_dollars(budget_net),
            "actual": _cents_to_dollars(actual_net),
            "variance": _cents_to_dollars(actual_net - budget_net),
            # Net income is favorable when actual >= budget (more profit than planned).
            "favorable": actual_net >= budget_net,
        },
    }


def trailing_margin_pct(point: TrailingPoint) -> float | None:
    """net income ÷ revenue × 100 (net margin). None on a 0/absent revenue base."""
    if not point.revenue_cents:
        return None
    return round(point.net_income_cents / point.revenue_cents * 100, 2)


def trailing_12_totals(points: list[TrailingPoint]) -> dict:
    """Trailing-12 revenue + net-income totals (DOLLARS) and the blended net margin (percent)."""
    revenue = sum(p.revenue_cents for p in points)
    net = sum(p.net_income_cents for p in points)
    margin = round(net / revenue * 100, 2) if revenue else None
    return {
        "revenue": _cents_to_dollars(revenue),
        "net_income": _cents_to_dollars(net),
        "net_margin_pct": margin,
        "months": len(points),
    }


def _goal_to_json(goal: AnnualGoal) -> dict:
    # usd goals carry cents internally; emit dollars at the boundary (everything else unchanged).
    to_display = (lambda v: _cents_to_dollars(v)) if goal.unit == "usd" else (lambda v: v)
    return {
        "key": goal.key,
        "label": goal.label,
        "unit": goal.unit,
        "target": to_display(goal.target),
        "actual": None if goal.actual is None else to_display(goal.actual),
        "higher_is_better": goal.higher_is_better,
        "on_track": goal_on_track(goal),
        "attainment_pct": goal_attainment_pct(goal),
    }


def _line_to_json(line: BudgetLine) -> dict:
    return {
        "key": line.key,
        "label": line.label,
        "kind": line.kind,
        "budget": _cents_to_dollars(line.budget_cents),
        "actual": _cents_to_dollars(line.actual_cents),
        "variance": _cents_to_dollars(line_variance_cents(line)),
        "variance_pct": line_variance_pct(line),
        "favorable": line_favorable(line),
    }


def _trailing_to_json(point: TrailingPoint) -> dict:
    return {
        "month": point.month,
        "revenue": _cents_to_dollars(point.revenue_cents),
        "net_income": _cents_to_dollars(point.net_income_cents),
        "net_margin_pct": trailing_margin_pct(point),
    }


def business_plan_to_json(plan: BusinessPlan) -> dict:
    """Serialize the business plan to the example-JSON contract the frontend builds to. Every money
    figure is in DOLLARS; goals/lines/trailing carry their derived on_track/variance/margin."""
    return {
        "company": plan.company,
        "fiscal_year": plan.fiscal_year,
        "period_label": plan.period_label,
        "annual_goals": [_goal_to_json(g) for g in plan.annual_goals],
        "budget_to_actual": {
            "lines": [_line_to_json(line) for line in plan.budget_lines],
            "totals": budget_to_actual_totals(plan.budget_lines),
        },
        "trailing_12": {
            "points": [_trailing_to_json(p) for p in plan.trailing_12],
            "totals": trailing_12_totals(plan.trailing_12),
        },
    }
