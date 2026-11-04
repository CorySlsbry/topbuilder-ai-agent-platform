# Incident Response Plan — Top Builder AI

_Operated by Salisbury Bookkeeping, LLC · Last updated 2026-06-14_

This document is the breach-notification and incident-response (IR) process for Top Builder AI. It
defines what counts as an incident, the lifecycle we follow, who does what, and the windows within
which we notify affected customers and authorities. It is written to be runnable under pressure —
when an incident is live, follow it top to bottom.

## Scope

Applies to any security or privacy incident affecting the Top Builder AI marketing site, the web
application and API, the booking service, or the customer data we process (including data in our
Supabase/AWS database, Google Cloud infrastructure, and the AI subprocessors Anthropic and
ElevenLabs).

## What is an incident?

A **security incident** is any confirmed or reasonably suspected event that compromises the
confidentiality, integrity, or availability of the platform or customer data. Examples:

- Unauthorized access to, or exfiltration of, customer data (including a cross-tenant data leak).
- Compromise of credentials, secrets, API keys, or a subprocessor account.
- A vulnerability confirmed to have been exploited (see [VULNERABILITY_DISCLOSURE.md](./VULNERABILITY_DISCLOSURE.md)).
- Malware, ransomware, or unauthorized code execution on our infrastructure.
- Loss/availability events that risk data integrity (corruption, accidental deletion).

A **personal-data breach** is a subset: an incident leading to accidental or unlawful destruction,
loss, alteration, unauthorized disclosure of, or access to, personal data.

## Severity levels

| Sev | Definition | Examples |
|---|---|---|
| **SEV-1 (Critical)** | Confirmed customer-data exposure, active exploitation, or full service outage. | Cross-tenant data read confirmed; credential vault decrypted by an attacker; database exfiltration. |
| **SEV-2 (High)** | Likely-exploitable exposure with limited blast radius, or partial outage. | A single account compromised; an exposed secret with no confirmed use. |
| **SEV-3 (Moderate)** | Security issue with no confirmed data impact. | Misconfiguration found internally before exploitation. |
| **SEV-4 (Low)** | Minor/no customer impact. | Non-exploitable finding; informational. |

The on-call lead may raise or lower severity as facts change; **default up** when uncertain.

## Roles

Top Builder AI is operated by a small team; roles may be held by one person but the function must be
covered for every incident.

- **Incident Lead (IL)** — owns the response end to end; the single decision-maker. Default: the
  founder/operator (Cory Salisbury).
- **Technical Lead** — drives containment, forensics, and remediation in the codebase/infra.
- **Comms Lead** — drafts and sends customer and authority notifications; the IL approves them.
- **Scribe** — keeps the incident timeline (see _Documentation_).

Primary contact for all of the above during an incident: **support@salisburybookkeeping.com**.

## Lifecycle

### 1. Detect

Sources: customer or researcher report (VDP inbox), Cloud Run / Supabase / GCP logs and alerts,
audit-log anomalies, subprocessor breach notice, or staff observation. **Anyone who suspects an
incident must report it immediately** to `support@salisburybookkeeping.com` — over-reporting is
expected and welcome.

On receipt: the IL opens an incident record, assigns a severity, and starts the timeline.

### 2. Contain

Stop the bleeding before investigating in depth. Depending on the incident, containment actions
include:

- Revoke or rotate the affected secrets and credentials (DB URL, JWT/webhook/cron secrets, the
  `CREDENTIAL_ENCRYPTION_KEY`, subprocessor API keys). See [CREDENTIAL_ROTATION.md](./CREDENTIAL_ROTATION.md).
- Disable the affected account(s), API token(s), or the dev-token path; force re-authentication.
- Flip the action master switch (`ACTIONS_ENABLED=false`) and/or set agents to advisory-only to
  freeze any write-back path.
- Block the offending IP/principal at the edge; tighten rate limits.
- If needed, take the affected service to a safe state (scale to zero / maintenance) — Cloud Run
  makes this a one-command operation.
- Preserve evidence first where feasible (snapshot logs/DB) so containment does not destroy
  forensic data.

### 3. Assess (eradicate + scope)

- Determine **root cause**, the **entry point**, and the **full blast radius**: which tenants, which
  data categories, how many records, and over what time window.
- Confirm whether **personal data** was involved and whether it was actually accessed/exfiltrated vs.
  merely exposed.
- Eradicate the cause: patch the vulnerability, remove attacker access/persistence, and verify the
  fix (add a regression test where the defect was code-level).
- Use the audit logs, RLS boundaries, and the deterministic-figure firewall to bound impact: figures
  cannot be silently altered by the LLM, and RLS limits cross-tenant reach — document what those
  controls did and did not prevent.

### 4. Notify

Notification is driven by the assessment. The IL decides, on advice of counsel where appropriate,
whether and whom to notify. Default posture is to **notify affected customers promptly and
transparently**.

**Affected customers**

- For any incident involving unauthorized access to or loss of a customer's data, notify the
  affected customer(s) **without undue delay and within 72 hours** of confirming the breach affects
  them.
- Notification (email to the account's admin contact + a follow-up) states, to the extent known:
  what happened, what data was involved, when it occurred and was discovered, what we have done to
  contain and remediate, what the customer should do (e.g. rotate connected-system credentials), and
  our contact for questions.
- We send a clear update even when the final root-cause analysis is still in progress.

**Authorities / regulators**

- Where a personal-data breach triggers a legal obligation, notify the relevant authority within the
  legally required window — e.g. **within 72 hours** of becoming aware for GDPR/UK-GDPR supervisory
  authorities, and within the applicable US state-law timelines for affected residents. As a
  processor for our business customers, we notify the customer (controller) promptly so they can meet
  their own regulatory deadlines, and assist them as required.

**Subprocessors**

- If a subprocessor (Supabase/AWS, Google Cloud, Anthropic, ElevenLabs) reports a breach to us, we
  fold it into this process and notify downstream as above.

### 5. Recover

- Restore affected services from known-good state; verify integrity (and restore from backup per
  [DISASTER_RECOVERY.md](./DISASTER_RECOVERY.md) if data was lost/corrupted).
- Increase monitoring on the affected surface for a defined watch period.
- Confirm the fix holds and the attacker has no residual access before declaring the incident
  resolved.

### 6. Post-mortem

Within **5 business days** of resolution, the IL produces a **blameless post-mortem** covering:
timeline, root cause, blast radius, what detection/containment worked and what did not, customer and
regulator notifications made, and a list of concrete **follow-up actions** with owners and dates.
Reusable lessons are pushed into our engineering log and security backlog so the same class of
incident cannot recur. Material lessons also feed the central build brain and the
`enterprise-security-audit` checklist.

## Notification timeline (summary)

| Audience | Window |
|---|---|
| Internal escalation to Incident Lead | Immediately on suspicion |
| Affected customers | Without undue delay, **within 72 hours** of confirming impact |
| Supervisory authority (where legally required) | **Within 72 hours** of awareness (GDPR/UK-GDPR); per state law for US residents |
| Post-mortem complete | Within **5 business days** of resolution |

## Documentation

The Scribe maintains a single incident record from detection to post-mortem: timestamped actions,
decisions and who made them, evidence collected, communications sent, and the final post-mortem.
Records are retained for at least 3 years.

## Testing this plan

We review this plan at least annually and after any SEV-1/SEV-2 incident, and run a tabletop
exercise periodically to keep the steps and contacts current.

---

_See also: [VULNERABILITY_DISCLOSURE.md](./VULNERABILITY_DISCLOSURE.md),
[SECURITY_POSTURE.md](./SECURITY_POSTURE.md), [CREDENTIAL_ROTATION.md](./CREDENTIAL_ROTATION.md),
[DISASTER_RECOVERY.md](./DISASTER_RECOVERY.md)._
