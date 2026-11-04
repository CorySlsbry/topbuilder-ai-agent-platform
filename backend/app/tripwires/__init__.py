"""Tripwire order capture — Stripe Payment Link sales of the low-ticket tripwire products.

Modules:
  * stripe_sig — PURE Stripe webhook signature verification (no stripe SDK).
  * service    — the checkout.session.completed handler: record (idempotent) -> Slack -> CRM sync.
  * crm_sync   — best-effort buyer upsert into the Salisbury CRM Postgres (fail-closed).
Persistence lives in app/repositories/tripwires.py (operator-global, migration 0029); the HTTP
surface in app/api/routes_tripwires.py.
"""
