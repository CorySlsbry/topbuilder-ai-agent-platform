# ADR 0006 — The 24/7 Booking agent: own the brain, not the voice

- **Status:** Accepted
- **Date:** 2026-06-03
- **Related:** [0003](0003-deterministic-analytics-llm-explains.md), [0005](0005-servicetitan-adapter-pattern.md)

## Context

The highest-ROI capability for a contractor is capturing **missed and after-hours calls** (27–62% of
calls go unanswered; 41% on weekends; each worth $285–$1,200; 85% who hit voicemail never call back).
This is the lead product. But a full voice stack — speech-to-text, telephony, voice synthesis,
real-time turn-taking — is a specialized, commoditized layer (Retell, Vapi, Bland, Synthflow, Twilio).
Rebuilding it would be a distraction and a worse product than buying it.

## Decision

Top Builder AI owns the **booking brain**, not the voice layer.

- The **voice/telephony provider** answers the live call (or an SMS/web form is filled), and POSTs a
  structured intake (caller, phone, zip, trade, intent, urgency, transcript) to our existing
  **signature-verified webhook → `event_queue`** (ADR-0005 infra, already built).
- The **Booking agent** consumes those intakes and runs a **deterministic engine** (ADR 0003):
  1. **Qualify** — real service request vs. spam/wrong-number/sales; in service area; trade we serve.
  2. **Slot** — find the soonest appropriate appointment given trade availability + urgency
     (emergency → today; routine → next open). Availability comes from the ServiceTitan adapter
     (the same technicians/appointments data the Workforce agent uses).
  3. **Value** — estimated recovered revenue per booking (by trade), and the headline metric:
     **after-hours revenue recovered** that would otherwise have been a missed call.
  4. **Book** — produces a **proposed** booking. Writing it back to ServiceTitan is **human-in-the-
     loop / advisory**: a draft awaiting dispatch confirmation, or an auto-book only with a signed
     approval policy. Consistent with the platform's advisory-only, read-by-default stance.
- The LLM **narrates** the call + recommendation; it never decides the numbers (qualification, slot,
  value are deterministic and tested).

## Consequences

- We ship the ROI driver fast by integrating a best-in-class voice provider behind a typed adapter
  (fixture + live skeleton), instead of building speech infra.
- The booking decision is deterministic, auditable, and offline-testable (fixtures of inbound calls →
  qualification + slotting + value), exactly like the other three agents.
- ServiceTitan stays protected: bookings are proposed/HITL, never silent writes.
- Reuses the webhook + event-queue, the ServiceTitan adapter, and the per-agent module template — so
  the build is mostly fixtures + formulas.
