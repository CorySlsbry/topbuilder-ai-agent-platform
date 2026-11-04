# Outreach email go-live (Resend on a dedicated sending subdomain)

The deliverability-safe way to email CRM contacts without burning `topbuilderai.com`. Sending is isolated
on a subdomain, gated by the action gate (ADR 0007), and compliance-checked by `app/outreach/compliance.py`.

Started 2026-06-24. Status: **code built + tested (fixture); live BLOCKED on a Resend API key.**

## Why a subdomain
Outreach reputation lives on **`send.topbuilderai.com`**, never the root. If a campaign trips a spam
filter, it burns the subdomain, not the website / booking / transactional mail. Visible From =
`outreach@send.topbuilderai.com`; **Reply-To must be a real monitored inbox** (the root has no MX) —
set `OUTREACH_REPLY_TO` to e.g. `cory.salisbury@gmail.com`.

> For COLD outreach at scale, a separate burner DOMAIN (not a brand subdomain) is the gold standard.
> We're honoring the subdomain choice for now; revisit if cold volume grows.

## Go-live sequence
1. **(Cory) Create a Resend account** (free tier) and put `RESEND_API_KEY=...` in
   `C:\Users\you\Downloads\Content Engine\.env`. This is the only step that needs a human (no account
   creation / login by the agent).
2. **(Agent) Add the domain via the Resend API** (`POST https://api.resend.com/domains`,
   `{"name":"send.topbuilderai.com"}`) → Resend returns the exact DNS records (the DKIM key is generated
   per-domain, which is why this must happen before the records are known).
3. **(Agent) Push the records to Cloudflare** (zone `topbuilderai.com`, all **DNS-only / grey cloud**):
   | Type | Name | Value | Notes |
   |---|---|---|---|
   | MX | `send` | `feedback-smtp.<region>.amazonses.com` (priority 10) | bounce/complaint return-path |
   | TXT | `send` | `v=spf1 include:amazonses.com ~all` | SPF |
   | TXT | `resend._domainkey.send` | `p=<public key from Resend>` | DKIM (exact value from step 2) |
   | TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:dmarc@topbuilderai.com` | DMARC; tighten to `p=quarantine` after warm-up |
4. **(Agent) Verify** the domain in Resend (it re-checks DNS) → status `verified`.
5. **(Agent) Warm up + send** through the action gate (see warm-up below).

## RESOLVED records (2026-06-24) — Resend domain CREATED (id a415af34-7c94-402a-8bc3-c8c42a02c74a)
The new full-access Resend key worked; `send.topbuilderai.com` is added (status not_started). Add these
4 records to the `topbuilderai.com` Cloudflare zone, all **DNS-only / grey cloud** (TXT/MX are unproxied
anyway). The `send.send` host is correct — it is the SES MAIL-FROM subdomain Resend uses for the bounce
return-path, not a typo. With `CLOUDFLARE_API_TOKEN` in `.env` I push all four via API + verify in one run.

| Type | Name (FQDN) | Value | Notes |
|---|---|---|---|
| TXT | `resend._domainkey.send.topbuilderai.com` | `REDACTED` | DKIM |
| MX | `send.send.topbuilderai.com` | `feedback-smtp.us-east-1.amazonses.com` (priority 10) | SES bounce return-path |
| TXT | `send.send.topbuilderai.com` | `v=spf1 include:amazonses.com ~all` | SPF |
| TXT | `_dmarc.topbuilderai.com` | `v=DMARC1; p=none; rua=mailto:cory.salisbury@gmail.com` | DMARC (monitor) |

**STATUS 2026-06-24 (latest):** all 4 records are in Cloudflare (DKIM/SPF/MX via the browser; Cory added
DMARC by hand). Resend verification: **SPF + MX = verified; DKIM = pending** but the DKIM TXT is confirmed
byte-for-byte correct in public DNS (Google DoH exact match) — pure resolver lag on the fresh subdomain;
it auto-verifies, no action needed. ⚠️ **DMARC has a typo**: Cory entered
`rua=mailto:support@person1@example.com` (double `@`, invalid email). p=none still works + DMARC is not
part of Resend's verification, so not blocking, but the report address is dead — fix the rua to a single
valid inbox e.g. `rua=mailto:cory.salisbury@gmail.com`. Re-check:
`GET https://api.resend.com/domains/a415af34-7c94-402a-8bc3-c8c42a02c74a` (do NOT spam POST /verify — each
call resets records to pending mid-recheck).

## Warm-up ramp (do NOT skip — cold-blasting a fresh subdomain is the #1 spam trigger)
`outreach_warmup_*` caps daily volume by the subdomain's age: `cap = start * growth^age_days`, clamped at
`outreach_daily_cap`. Defaults: start 20, growth 2, ceiling 2000 → day0 20, day1 40, day2 80 … day7 2000.
Send the most-engaged/likeliest-to-reply contacts first.

## Compliance posture (enforced in code, fail-safe)
`app/outreach/compliance.py` decides ALLOW/HOLD before anything sends, and the `send_outreach_email`
executor RE-CHECKS at execute time (defense in depth):
- **CAN-SPAM** — every message must carry a working unsubscribe + a physical postal address
  (`OUTREACH_PHYSICAL_ADDRESS`) + honest from/subject, or the whole batch is held.
- **HARD COUNTRY BLOCK (Cory's directive 2026-06-24): NEVER email Canada, even WITH consent.**
  `outreach_blocked_countries=CA` is checked first and overrides everything — a `country=CA` contact is
  always refused (`country_blocked:CA`), opted-in or not. Your Canadian relationships (Alex, Sam) are
  excluded from email; reach them another way. Add more ISO-2 codes to the setting to block them too.
- **Consent / jurisdiction (for everywhere not hard-blocked)** — opted-in contacts allowed; **cold
  contacts in remaining GDPR (EU/EEA) / UK jurisdictions are HELD**, never auto-sent; **cold + unknown
  jurisdiction is HELD** (fail-safe); US cold B2B is permitted under CAN-SPAM. Not legal advice.
- **Suppression** — unsubscribed / hard-bounced are always held.

## What's built (this session, fixture-verified, uncommitted)
- `app/outreach/compliance.py` — pure engine (CAN-SPAM, consent gate, suppression, warm-up). 22 tests.
- `app/integrations/email_send/` — Resend transport: fixture + live (real POST), fails closed w/o key.
- `app/actions/executors.py` — `send_outreach_email` (+ undo = suppress recipient); registered + allowlisted.
- `app/config.py` — `email_send_mode`, `resend_api_key`, `outreach_*` (From/Reply-To/address/warm-up/consent).

## Still to build (next slice)
- Migration: `email_suppression` (unsubscribed/bounced) + `outreach_sends` (sent log + daily-cap counter), RLS.
- Routes `/v1/outreach/*`: propose sends to selected ADS-CRM contacts through the action gate; a public
  one-click unsubscribe endpoint + signed token (writes to `email_suppression`).
- Frontend Outreach view; wire the propose path to the CRM contact list.
- List bounce-verification before the first cold batch.

## Cold outreach SEQUENCES + prospecting (2026-06-24) — separate track from the Resend/warm path
Two 10-email cold sequences written + tailored to the PLATFORM (not bookkeeping — Cory's directive):
`marketing/sequences/contractor-cold-sequence.md` (ServiceTitan owners) and
`marketing/sequences/cpa-partner-cold-sequence.md` (CPA referral partners, 20% recurring, Circular-230).
Tool-agnostic (paste the 10 steps into any sender). Current offer baked in: $3,000/mo entry, $0 install
this quarter, 30-day board-ready-or-free, book.topbuilderai.com. Both carry a `[physical mailing address]`
placeholder — Cory must supply the real address (CAN-SPAM).

**Sending decision (Cory chose):** COLD goes through **Apollo** (warmed dedicated cold mailboxes), NOT
through `send.topbuilderai.com`. The Resend subdomain stays reserved for WARM CRM-contact + transactional
mail — cold volume on the brand subdomain would risk its reputation. So the two tracks are separate.

**ICP validated live (Apollo, 1 credit):** `apollo_mixed_companies_search` with tags
[HVAC, plumbing, electrical, heating and air conditioning], revenue $3M-$30M, employees 11-200, US only,
**Canada excluded at query level** → **14,093 matching shops** (textbook ServiceTitan profile: Bonney,
Radiant Plumbing, Ragsdale/Wrench Group, Bell Brothers, J. Blanton). Apollo credits: 2,880 remaining.

**Why the 200-enrich was NOT run this session:** (1) the credit-saving dedup hits the JARVIS master-DB
API (`jarvis-ashy-kappa.vercel.app/api/master-db/dedup`, POST against the 326K-company Supabase) — a
network POST this session's tools can't reach; without it we'd risk paying to re-enrich known shops.
(2) Sending is 2-4 wks out (warm-up), so a dump today would go stale. → Run the full enrich as a focused
`construction-client-prospector` pass where dedup works, on a ~200-250/week cadence feeding the warm-up.
NOTE: that skill is stale (BuilderCFO/GHL framing + GHL contact creation) — run it **Apollo-only, no GHL**
(GHL is retired); contacts feed the Apollo SEQUENCE, not a GHL workflow.

**Critical path = mailbox warm-up (the real gate to "live"):** buy 2-3 dedicated cold domains (lookalikes,
NOT the brand root — e.g. trytopbuilderai.com), 2-3 Google/M365 mailboxes each (~6-9 inboxes), SPF/DKIM/
DMARC per domain, warm up 2-4 weeks (ramp ~5→~35/day per inbox → ~250/day fleet capacity), THEN connect to
Apollo + paste the sequence steps + load the prospected list. Human-gate the copy before any send.

**RESUME (2 unblock items):** (1) Cory supplies the physical mailing address. (2) Cory green-lights the
cold domains/mailboxes so warm-up starts (gates everything). Then: focused prospecting pass (dedup) →
build Apollo sequences from the two files → load list → send on the warm-up ramp.

### 2026-06-24 (later) — FIRST cold domain LIVE: trytopbuilderai.com (Google Workspace + Cloudflare DNS DONE)
Cory bought **trytopbuilderai.com** (~$11/yr, registered at Cloudflare zone `7ee133f3e34753f056e1eb6c3153c575`)
as the first dedicated cold-send lookalike (NOT the brand root — protects topbuilderai.com reputation).
Agent drove the Chrome MCP to complete the email-auth stack (verified live):
- **Cloudflare DNS** (6 records): MX `smtp.google.com`; SPF `v=spf1 include:_spf.google.com ~all`;
  DMARC `_dmarc` = `v=DMARC1; p=none; rua=mailto:cory.salisbury@gmail.com`; DKIM `google._domainkey`;
  google-site-verification TXT. Google auto-pushed MX+DKIM+verification via **Domain Connect**; agent
  added SPF + DMARC by hand. (Harmless dup MX both→smtp.google.com, pri 1 + 10 — optional cleanup.)
- **Google Workspace**: Gmail ON for everyone; **DKIM authentication STARTED** in Admin → Apps → Gmail →
  Authenticate email (status now "Authenticating email with DKIM").
- **Gotcha:** Google's setup opens a Cloudflare **Domain Connect "apply"** tab carrying `spfrule=include:_spf.google.com`.
  Do NOT click Apply after manually adding SPF — it creates a 2nd SPF record (multiple SPF = BROKEN SPF).
  Use "Switch to manual verification" instead. Sending ESPs (Resend) PROHIBIT cold outreach in AUP (verified:
  "unsolicited messages of any kind, including cold outreach" → account termination) — cold goes via this
  Workspace-inbox + Instantly/Smartlead path, NOT Resend/send.topbuilderai.com (that stays warm/transactional).
- **RESUME:** Cory creates 2-3 mailboxes (cory@, cory.salisbury@) + passwords; connect to Instantly/Smartlead;
  start ~2-wk warm-up (ramp ~5→35/day/inbox). Then load the prospected list + paste the 2 sequences. Add 2 more
  lookalike domains later to scale toward 200/day. Tighten DMARC to p=quarantine after warm-up.
