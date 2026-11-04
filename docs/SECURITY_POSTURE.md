# Security Posture — Top Builder AI (updated 2026-06-10)

The current controls, the auth/2FA design, and the prioritized hardening backlog.

## 1. Authentication (NEW — Supabase Auth + TOTP 2FA)

- **IdP:** Supabase Auth on the platform project (`zoprshhdvvyhbnltttyt`). Email+password sign-in;
  access tokens are **ES256-signed** and the API verifies them against the project **JWKS**
  (`/auth/v1/.well-known/jwks.json`) — no shared secrets, keys rotate server-side.
- **Identity → tenant/role:** the token carries identity only. The API resolves tenant + role from
  the **`user_memberships` directory** (migration 0013, e-mail invite pattern; `auth_user_id`
  backfills on first login). No membership ⇒ 401. Customers can never pick their tenant or role.
- **2FA (TOTP):** enrollment + challenge in the dashboard Security panel (Supabase MFA). The token's
  `aal` claim reflects it; **`require_admin` demands `aal2` server-side** — operator/admin access
  (action approve/execute, learning approvals, Email/SEO agents, membership admin) is impossible
  without a verified authenticator code, even with a stolen password.
- **Roles:** `admin` (operator; 2FA-required) · `analyst` (runs agents) · `viewer` (read-only).
- **Demo coexistence:** `AUTH_MODE=dev` accepts demo dev-tokens AND real Supabase logins (hybrid).
  Real go-live flips `AUTH_MODE=supabase`, which kills dev tokens entirely in one env change.
- **Operator path (Cory):** seeded admin invites for `cory.salisbury@gmail.com` and
  `support@topbuilderai.com` (apex tenant). Sign up with either e-mail → enroll TOTP → operator.
  New customers: `POST /v1/admin/memberships` {email, tenant, role} (operator-only).

## 2. Existing controls (verified)

| Layer | Control |
|---|---|
| Tenant isolation | Postgres **RLS, FORCE, fail-closed** on all 16 tenant tables; app connects as non-superuser `app_user`; transaction-local GUC (proven: cross-tenant read → 404) |
| Transport | HTTPS everywhere (Cloud Run managed TLS) |
| Secrets | GCP Secret Manager (JWT secret, DB URL, encryption key, webhook secret, cron secret); never in code/git |
| Credentials at rest | Fernet-encrypted vault for tenant ST/QBO creds (`CREDENTIAL_ENCRYPTION_KEY`) |
| Webhooks | HMAC signature verification (`WEBHOOK_SIGNING_SECRET`), fail-closed |
| Cron endpoints | Shared-secret header (`X-Cron-Key`), 404 when unconfigured |
| Write path | ADR-0007 gate: propose → approve (admin+2FA) → execute, idempotent, undo, audited; master switch `ACTIONS_ENABLED=false` |
| Rate limiting | Token-bucket per principal (in-process; Redis-able interface) |
| LLM safety | ADR-0003: deterministic figures, narration-only LLM; learning layer structurally firewalled + eval-gated + canaried |
| CORS | `ALLOWED_ORIGINS` locked to the dashboard + topbuilderai.com (was `*`) |
| Operator tools | Email/SEO agents + membership admin: `require_admin` (role + aal2) |

## 3. Frontend security

- Tokens held in memory/Supabase session storage; API calls Bearer-only (no cookies ⇒ no CSRF surface).
- The Operator nav is UI-gated (`?superadmin=1`) **and** server-enforced (the UI flag alone grants nothing).
- 2FA enrollment UX: QR + manual secret; operator accounts see a blocking "2FA required" banner.
- No secrets in the bundle: the Supabase **publishable** key is public-by-design; config comes from
  `GET /auth/config`.

## 4. Hardening backlog (priority order)

1. **Flip `AUTH_MODE=supabase`** at customer go-live (kills dev-tokens; demo moves to seeded demo accounts).
2. **Supabase Auth settings** (dashboard, one-time): leaked-password protection ON, e-mail confirmations
   ON (default), rate limits review. Optional: disable public signups once invite-only is preferred.
3. Redis-backed rate limiting (global across instances) + per-tenant quotas.
4. Audit log review surface for `agent_actions` + auth events in the operator dashboard.
5. Dependency scanning (pip-audit / npm audit) in CI; Cloud Run egress policy; budget alerts.
6. Pen-test the action gate + RLS with a real tenant before the first $50k client.
