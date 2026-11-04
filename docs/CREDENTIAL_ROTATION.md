# Credential / Key Rotation + Compromise Response

How Top Builder AI rotates the credentials it stores on a customer's behalf, and what we do if a key
or a stored token is ever compromised. This is the operational answer to the Procore / ServiceTitan
partner question *"how are credentials rotated, and what is your process if compromised?"*

## What we store, and how it's protected

| Secret | Where | Protection |
|---|---|---|
| Per-tenant ServiceTitan / QuickBooks / provider tokens | `tenant_credentials.secret_ciphertext` (Postgres, RLS-isolated per tenant) | **AES-256-GCM** field encryption (`app/crypto.py`), key = `CREDENTIAL_ENCRYPTION_KEY` |
| Platform secrets (JWT signing, webhook MAC, DB DSN, vault key itself) | Google **Secret Manager**, scoped to the Cloud Run compute SA | Managed AES-256 at rest + IAM |
| Everything at rest | Supabase/Postgres on AWS + Cloud Run | AES-256 storage layer (defense in depth, under the field encryption) |

The vault key (`CREDENTIAL_ENCRYPTION_KEY`) is a urlsafe-base64 **32-byte (AES-256)** key. It lives
only in Secret Manager — never in the database, the image, or the repo. Each ciphertext is
`v2:gcm:` + base64(96-bit nonce ‖ ciphertext ‖ auth tag), with a fresh random nonce per write.

## How rotation works (the two-key window)

The cipher supports **primary-encrypt / many-keys-decrypt** so rotation is zero-downtime and needs no
data-migration outage:

- `CREDENTIAL_ENCRYPTION_KEY` — the **primary** key. *Every encrypt uses it.*
- `CREDENTIAL_ENCRYPTION_KEY_OLD` — optional, comma-separated list of **retired** keys accepted for
  **decrypt only**. While this is set, ciphertext written under a previous key still reads back, so
  the app keeps working the instant the primary key changes — before the data has been re-encrypted.

`app.crypto.rotate_ciphertext(old_ciphertext)` decrypts with the primary key, any retired key, or the
legacy Fernet path, and re-encrypts under the **current primary** key. The sweep script
`backend/scripts/rotate_credentials.py` applies it to every stored secret. It is **idempotent**
(re-encrypting already-primary ciphertext just re-nonces it) and **RLS-scoped** (it iterates tenants
and re-encrypts each tenant's rows under that tenant's `app.current_tenant`, with no superuser bypass).

## Routine rotation runbook (scheduled, e.g. every 90 days)

1. **Generate a new key.**
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   (Fernet's key is exactly 32 urlsafe-base64 bytes = a valid AES-256 key.)

2. **Stage both keys.** Move the *current* key value into `CREDENTIAL_ENCRYPTION_KEY_OLD` and set the
   *new* key as `CREDENTIAL_ENCRYPTION_KEY` (both via Secret Manager → the Cloud Run service env).
   Deploy. The app now **encrypts with the new key and still decrypts the old ciphertext**, so there
   is no read outage.

3. **Sweep the vault.** Run the re-encryption inside the api container (it has asyncpg + the app):
   ```bash
   # dry-run first — reports counts, writes nothing:
   python scripts/rotate_credentials.py --dry-run
   # then the real sweep (demo tenants by default; pass --tenant <uuid> ... for explicit tenants):
   python scripts/rotate_credentials.py
   ```
   Every `secret_ciphertext` is re-encrypted under the new primary key. (The script also discovers and
   sweeps any `*_ciphertext` / `*_encrypted` columns on `servicetitan_connections` if that table ever
   stores encrypted tokens — it tolerates a schema that has none.)

4. **Retire the old key.** Once the sweep is clean, **remove** `CREDENTIAL_ENCRYPTION_KEY_OLD` and
   redeploy. The retired key is now fully out of service; destroy that Secret Manager version.

5. **Verify.** Read back a credential (e.g. `GET /v1/connections` metadata + an agent live-mode call)
   and confirm decryption still works under the new-only key.

## Compromise response

If the vault key, a service-account credential, or a stored customer token is suspected compromised:

1. **Contain.** Set `ACTIONS_ENABLED=false` (advisory-only — no writes leave the platform) and, if the
   leak is the vault key, treat **all** stored tokens as exposed.
2. **Rotate the vault key immediately** using the runbook above (new primary, old key in
   `_OLD`, sweep, retire) — this re-encrypts every secret under a key the attacker does not have.
3. **Rotate the upstream credentials at the source.** A re-encrypt does not help if the *plaintext*
   token leaked, so **revoke and reissue at the provider**: rotate the ServiceTitan client secret /
   app key, the QuickBooks OAuth tokens, and the Procore OAuth client secret + refresh token. Update
   the per-tenant vault entries with the reissued secrets, then re-run the sweep.
4. **Rotate platform secrets** if they were in scope: `JWT_SECRET`, `WEBHOOK_SIGNING_SECRET`, the
   `app_user` database password, and the DSN. (JWKS/OIDC signing keys rotate at the IdP.)
5. **Invalidate sessions.** Rotating `JWT_SECRET` / IdP keys invalidates issued tokens; force re-auth.
6. **Audit + notify.** Review the audit log (`docs/AUDIT_LOGGING.md`) for the exposure window, scope
   the blast radius (which tenants, which providers), and notify affected customers per contract /
   regulatory obligations.
7. **Post-incident.** Confirm the old key/secret versions are destroyed in Secret Manager and record
   the incident + timeline in `docs/ENGINEERING_LOG.md`.

## Config reference

| Setting | Purpose |
|---|---|
| `CREDENTIAL_ENCRYPTION_KEY` | The **primary** AES-256 vault key. Required. Every encrypt uses it. |
| `CREDENTIAL_ENCRYPTION_KEY_OLD` | Optional, comma-separated **retired** keys, decrypt-only, kept set only during a rotation window. |

Code: `backend/app/crypto.py` (`CredentialCipher`, `rotate_ciphertext`, `get_cipher`) ·
`backend/scripts/rotate_credentials.py` (the sweep) · `backend/tests/test_crypto.py` (rotation tests).
