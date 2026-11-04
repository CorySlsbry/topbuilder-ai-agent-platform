# Procore App Listing — content pack (App Settings + Configuration Builder)

Paste-ready copy for the **Procore Developer Portal** app: the App Settings fields (descriptions,
post-install notes), the Configuration Builder Instructions Page, and the Data Connector Component
recommendation. Every claim below is TRUE to what Top Builder AI is and does today (read-first /
advisory, deterministic figures, human-approved writes). Keep this in sync with
`brand/BRAND_MESSAGING.md` and `docs/PROCORE_FORM_FILL.md`.

Support: **support@topbuilderai.com** · Booking: `https://topbuilder-ai-booking-840472456279.us-central1.run.app`
Posture: read-only by default; any write-back is proposed → human-approved → executed → audited & reversible.

---

## 1. Instructions Page — Name

> **Install & Setup Guide**

(Short alternates if a tighter label is needed: "Setup Guide" · "Connect Procore".)

---

## 2. Instructions Page — Body (Configuration Builder)

Paste into the Instructions Page rich-text body. Plain, operator-to-operator, no hype.

```
Install & Setup Guide

Top Builder AI is the AI back office for contractors. Six self-learning agents — Booking,
Routing & Dispatch, Financial, Inventory, Workforce, and Documents — read your Procore project,
financial, and document data and turn it into deterministic, audited recommendations your
back-office team reviews and approves.

What this app does
- Reads your Procore data (projects, financials, documents, field productivity) on a scheduled basis.
- Computes the numbers with deterministic, tested code — the AI narrates the result, it never
  invents a figure.
- Surfaces recommendations in the Top Builder AI dashboard for your team to review.

Read-only by default. Top Builder AI does not write back to Procore unless you turn it on. Any
write-back is proposed first, approved by a person, then executed — and every action is audited
and reversible.

Setup (about 5 minutes)
1. Click Authorize / Install and sign in with a Procore account that can grant the requested
   read access.
2. Approve the read-only permission template when Procore prompts you. Procore stays your system
   of record — we only read.
3. Open the Top Builder AI dashboard (link sent to your install email) and choose which agents
   and departments are active.
4. Recommendations begin populating after the first scheduled data sync. Review them, approve or
   edit, and the agents learn your shop from your corrections.

Need help? Email support@topbuilderai.com and the developer will respond directly.
```

---

## 3. Post-Installation Notes — VERBATIM

Paste this exactly into the App Settings "Post-Installation Notes" field (the text Procore shows the
user immediately after install).

```
Authorization complete — Top Builder AI is now connected to your Procore account.

Your back-office team reviews the agents' recommendations in the Top Builder AI dashboard (the
link is in your install email). Top Builder AI reads your Procore data on a scheduled basis;
all access is read-only by default and Procore remains your system of record — we never write
back unless you explicitly enable it, and any write is proposed, human-approved, audited, and
reversible.

In the dashboard, choose which agents (Booking, Routing & Dispatch, Financial, Inventory,
Workforce, Documents) and which departments are active for your team. Recommendations begin
populating after the first scheduled data sync.

Questions or help getting started? Email support@topbuilderai.com.
```

---

## 4. App Description

### Short description (≤120 chars)

> **AI back office for contractors: six self-learning agents read your Procore data to surface margin, materials & labor early.**

(118 chars. Alternate, 99 chars: "Six AI agents read your Procore data to catch margin leaks, unbilled materials, and labor risk early.")

### Long description (marketplace)

```
Top Builder AI is the AI back office for contractors — six self-learning agents that turn your
Procore data into clear, audited recommendations, so you see profit and risk early instead of at
month-end.

Procore runs the project. Top Builder AI runs the back-office analysis Procore was never built to
do — Money, Materials, People, and Paperwork:

• Financial — projects 30/60/90-day cash and flags margin leakage the day it appears.
• Inventory — reorder points, shrinkage alerts, and unbilled materials.
• Workforce — forecasts understaffing and avoidable overtime a week out, by trade and crew.
• Routing & Dispatch — drive-time-optimized assignments that also weigh margin, parts, and overtime.
• Booking — qualifies, slots, and values every inbound call, including after-hours.
• Documents — classifies, extracts, and files inbound documents to the right project and folder.

Built for trust:
• Read-only by default. Procore stays your system of record. Any write-back is proposed, approved
  by a person, executed, and fully audited and reversible.
• Deterministic figures. Every number is computed by unit-tested code — the AI only explains the
  result, it never computes a figure. The math stays exact and auditable.
• Self-learning, on a leash. The agents learn from the corrections your team approves, governed by
  a safety + regression eval gate and a human approval queue before any change goes live.
• Per-customer isolation. Row-level data isolation and encrypted credentials; your learned rules
  never leave your account and never train another company's agents.

Authorize from Procore, choose which agents and departments are active in the Top Builder AI
dashboard, and your back-office team starts reviewing recommendations after the first sync.

Questions? support@topbuilderai.com
```

---

## 5. Data Connector Components — recommendation

**Use the Service Account (Client-Credentials / Data Connection Managed Service Account, "DMSA")
method, not user-based 3-legged OAuth**, for our integration. Our data sync is read-first,
scheduled (batch), and runs with no user in the loop — exactly the pattern Procore's Service-Account /
Data Connection app model is built for. The customer grants a single, company-scoped, **read-only
permission template** to the service account; access doesn't break when an individual employee leaves
or loses a session, and the connection survives unattended overnight syncs.

### The tradeoff (state in the listing / config notes)

| | Service Account (Client-Credentials / DMSA) — **recommended** | User OAuth (3-legged, Authorization Code) |
|---|---|---|
| Who authorizes | A company admin grants a company-scoped, read-only permission template once | Each user logs in and consents individually |
| User in the loop | None — ideal for scheduled, unattended reads | Required; tied to a person's session/login |
| Token lifecycle | Stable service-account credential; no per-user refresh churn | Per-user refresh tokens; access ends when the user leaves |
| Best for | Read-first, batch/scheduled data sync (our model) | Actions performed in the context of a specific signed-in user |
| Scope | Least-privilege, read-only template at the company level | The granting user's own permissions |

**Why it fits us:** Top Builder AI reads on a schedule and computes deterministically; nothing in
the core sync needs a live human session, so a service account with a read-only template is the
lowest-friction, most resilient, least-privilege connection. We keep 3-legged Authorization Code
OAuth available for any future user-context, write-back action — which is always gated behind a
human approval step regardless of grant type.

> Verify Procore's exact terminology at wiring time — Procore's "Data Connection" apps use a
> Service Account / DMSA (client-credentials) grant; confirm the current label and the available
> read-only permission templates in the Developer Portal when configuring the app.
