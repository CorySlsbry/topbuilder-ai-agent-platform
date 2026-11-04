# QuickBooks Online — OAuth Scope Decision (LOCKED)

This is the **owner's decided position** on what entitlement Top Builder AI requests from QuickBooks
Online (Intuit) for **Summit Heat Pumps** (and the standing default for every contractor tenant).
It exists so the scope cannot silently drift; the decision is **guarded by a test**
(`backend/tests/test_qbo_scope.py`) that fails CI if anyone widens it without updating this doc.

**Status:** DECIDED — `Settings.quickbooks_scopes = "com.intuit.quickbooks.accounting"` (already set in
`backend/app/config.py`). This document records *why*; the guard test enforces *that*.

---

## The decision

### 1. Entitlement = Accounting API, READ-ONLY (`com.intuit.quickbooks.accounting`)

We request **exactly one** OAuth scope: `com.intuit.quickbooks.accounting`. The Financial agent uses it
to **read** the company file — AR/AP aging (summary + detail), open invoices, the balance sheet, and the
profit & loss — to power the Finance half of the scorecard and Alex's bookkeeping work
(`docs/QBO_DATA_MAP.md` §2 maps every KPI to its exact Reports/Query call). All reads are deterministic
(ADR-0003); any future QBO *write* (e.g. apply a `Payment`, send a statement) goes through the
human-approved action gate (ADR-0007), **not** through a broader OAuth grant by default.

We **do NOT** request:

- **`com.intuit.quickbooks.payment`** — we do not process card payments through Intuit. Requesting it
  would put a payments-data surface on the consent screen we have no use for.
- **`openid` / `profile` / `email`** (OpenID Connect / sign-in-with-Intuit) — identity comes from our own
  IdP/JWKS auth; Intuit identity is not needed to read the company file. The `realmId` returned on the
  OAuth callback already binds the connection to the contractor's company.

Either scope may be added **later** only if a concrete future surface needs it — and only by updating
this doc and the guard test in the same change. Minimizing scope keeps the consent screen honest and the
blast radius of a leaked token small (read-only accounting, no payments, no identity).

### 2. We do NOT use QBO Payroll — payroll lives in ServiceTitan

Payroll is **not** sourced from QuickBooks. It is computed by our ServiceTitan-side
**BC-overtime payroll engine** (`backend/app/agents/workforce/payroll.py` — the BC/CA overtime rules +
pay classes + claimed-vs-clocked gap), and the only payroll *write* is the gated `payroll_adjustment`
write-back through the action gate. QBO is **finance-only** in this product. Concretely this means we
never request a QBO Payroll scope and never call the QBO Payroll endpoints — payroll figures must reconcile
to ServiceTitan time data, the system of record for the field crew, not to a second payroll ledger in QBO.

### 3. LiveFlow is replaced — natively, from the QBO P&L

Alex previously kept his **budget-to-actual** and **trailing-12 P&L trend** in **LiveFlow** (a QBO add-on).
We **replace LiveFlow** entirely: those two surfaces are produced **natively** by our pure EOS
business-plan engine (`backend/app/org/eos.py` — `budget_to_actual_totals`, `trailing_12_totals`,
`business_plan_to_json`) from the **QBO `ProfitAndLoss` report** (read via the one accounting scope above;
`docs/QBO_DATA_MAP.md` §3.2). **No LiveFlow. No Zapier. No third-party connector** — a direct, first-party,
deterministic read, consistent with the hard "NO iPaaS" constraint (`docs/QBO_DATA_MAP.md` §0/§4).

### 4. Sandbox → production flip happens at go-live

The OAuth authorize/token **hosts are identical** for sandbox and production (Intuit routes by client id);
only the **API base host** and the pinned **`minorversion`** differ:

- Sandbox: `https://sandbox-quickbooks.api.intuit.com/v3/company/{realmId}/...`
- Production: `https://quickbooks.api.intuit.com/v3/company/{realmId}/...` (current
  `Settings.quickbooks_base_url` default)

At go-live we flip `Settings.quickbooks_environment` (`sandbox` → `production`) and point
`quickbooks_base_url` at the production host, and pin/confirm `minorversion` on the target company. **This
flip does not change the OAuth scope** — the accounting-only, read-only entitlement above is the same in
both environments. (Per-tenant go-live steps live in `docs/QBO_DATA_MAP.md` §5 and the go-live runbook.)

---

## How this is enforced

`backend/tests/test_qbo_scope.py` asserts, against the real `Settings`/`qbo_oauth` code (no mocks of the
value):

1. `Settings().quickbooks_scopes == "com.intuit.quickbooks.accounting"` (exact, accounting-only);
2. the scope string contains neither `"payroll"` nor `"payment"`;
3. `qbo_oauth._scope_list(Settings())` == `["com.intuit.quickbooks.accounting"]` (the parsed list);
4. `qbo_oauth.build_authorize_url(...)` puts that scope — and only that scope — into the consent URL.

If a future change widens the scope, that test fails: update **this doc** and the test **together**, as a
deliberate, reviewed decision — never a silent drift.

## See also

- `docs/QBO_DATA_MAP.md` — the full direct-OAuth data map (endpoints, scopes, KPI → call, reliability).
- `backend/app/config.py` — `quickbooks_scopes` (the locked default) + the clarifying comment.
- `backend/app/integrations/quickbooks/qbo_oauth.py` — `_scope_list` / `build_authorize_url`.
- `backend/app/org/eos.py` — the native budget-to-actual + trailing-12 engine that replaces LiveFlow.
- ADR-0003 (deterministic figures), ADR-0005 (fail-closed live integrations), ADR-0007 (gated writes).
