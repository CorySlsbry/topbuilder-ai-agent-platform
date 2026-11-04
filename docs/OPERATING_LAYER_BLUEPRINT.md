# Top Builder AI — the Operating Layer (Premium Blueprint)

> ServiceTitan is the system of record. **Top Builder AI is the intelligence + control layer on top
> of it.** Your people work in our cockpit; the agents read and write ServiceTitan in the background.
> You change how the business runs *from inside the system*.

## Vision

A department-wide AI business manager that sits on ServiceTitan and runs the operational spine —
answering calls, booking, routing, documents, field ops — with every agent action signed, logged, and
reversible. Two skins: a dark, dense **Command Center** and a light **Easy Mode**.

## Architecture (layers)

1. **Agent spine (built):** LangGraph agents, deterministic engines + LLM-narrates (ADR 0003),
   Postgres RLS multi-tenancy, the human-approved **action gate** (ADR 0007: propose → approve →
   execute, audited, idempotent).
2. **Autonomy policy (Phase 1):** per-tenant, **per-agent switch** — `off` / `hitl` / `auto`
   (autonomous-with-undo). Replaces the global `ACTIONS_ENABLED`. Humans can edit agent output and
   supply **feedback that trains** the agent (stored, fed back via the Learn/RAG module).
3. **Operating data (Phase 1):** Communications (calls/SMS/email/voicemail/web — 2-way, through
   ServiceTitan when live), Tasks (agent-generated worklist + ST sync), Documents (store / organize /
   generate / extract / e-sign — filed to the right customer/department in ST), Dispatch/Routing.
4. **Knowledge feed:** feed each agent via **document/Excel upload** *and* **in-system prompting**.
   (RAG "Learn" module exists; extended per-agent.)
5. **Surfaces:** role-aware **Command Center** (Next.js → desktop via **Tauri**, + PWA) and a
   **mobile field-ops app** (Expo/React Native) — techs see jobs, status, photos, checklists, time,
   and build a **custom quote** by adding/removing services.

## Stack decision (the 0.1% call)

- **Backend:** FastAPI + LangGraph + Postgres/pgvector (keep — proven, fast, the AI spine).
- **Web/desktop:** Next.js command center, installable as a **Tauri** desktop app (tiny/native, runs
  where ServiceTitan runs) + PWA. v1 ships as the fast web/PWA so we're never blocked; Tauri is a
  fast-follow.
- **Mobile (field):** Expo/React Native, sharing TypeScript types with the web.
- **Realtime:** SSE/WebSocket for the live board + live calls (after v1 polling).
- **ServiceTitan:** typed read/write adapter — fixtures now, live OAuth2 app per client later. Writes
  go through the autonomy policy + action gate. Advisory where the user chose advisory (routing).

## Agent roster (each with an autonomy switch)

Booking (24/7) · **Routing/Dispatch** · Communications · Documents · Workforce · Financial · Inventory.

## Department views

Owner/GM · **Dispatch** · **Front-Desk/CSR** · Field Tech (mobile) · Finance · Sales/Estimating ·
Inventory. Each role sees only what it needs (cognitive-load reduction); RLS + role scope enforce it.

## Roadmap

- **Phase 1 — the spine (in progress):** Routing/Dispatch agent · per-agent autonomy policy ·
  Communications + Tasks backend · Command-Center shell with **Dispatch** + **Front-Desk** views
  (dark + light skins).
- **Phase 2:** Documents agent (store/organize/generate/extract/e-sign, filed in ST) · the
  feedback/train loop + document/Excel/prompt feed · remaining department views.
- **Phase 3:** Live-call layer (AI answers missed/after-hours calls — telephony provider) · 2-way
  comms through ServiceTitan · ServiceTitan write-through (go-live).
- **Phase 4:** Mobile field-ops app (Expo) · Tauri desktop packaging · realtime board.
- **Demo:** seeded fixtures across departments + a scripted **demo video** for the website (Remotion).

## Operating principles (non-negotiable)

Deterministic compute + LLM-narrates · per-agent autonomy with undo · everything audited + RLS-isolated
· advisory-by-default, execute-on-policy · tested to a hand-computed oracle before it ships.

## The $50k bar (the enforced standard — every remaining piece is built to this)

This is a **$50,000 enterprise upgrade** to a contractor's systems. It sells Relief, Authority, and
Speed, never price. Each piece clears this bar before it ships — not as a retrofit:

1. **Real, not demo.** Fixtures are for the sales demo only. The delivered system runs on the client's
   **live ServiceTitan + QuickBooks** data, per-tenant, with **zero static/placeholder data**. Every
   client starts clean and isolated. **`production-readiness-audit` is the go-live gate** (fresh-start
   per signup, per-account isolation, security blockers closed, smoke-tested on the deployed instance).
2. **Never breaks silently.** Deterministic figures, fail-closed RLS, idempotent writes, every agent
   action signed/logged/reversible, self-healing where it touches external systems.
3. **Feels expensive.** Agency-tier visual craft (`high-end-visual-design` + `design-taste-frontend`):
   depth, typographic hierarchy, intentional spacing, micro-interactions, command-center gravity — no
   default-component / generic-admin-panel look.
4. **Removes cognitive load.** Each role opens to "what needs you now," not raw dashboards. The buyer
   pays precisely so they do not have to think.
5. **White-glove onboarding.** Connecting ServiceTitan (the per-client dev app) is a bespoke, done-for-
   them step — elite filtration, not a self-serve form.
6. **Operating system, not software.** Proprietary naming + transformational value (~$200K+/yr handed
   back) + time/reputation guarantees in the offer (compose `Premium` + `hormozi-advisor` + `dante`/`tj`).
7. **The asset that sells it:** a scripted **demo video** (Remotion) for topbuilderai.com.
