# Unit Economics — "are the 6 agents covered?"

**Question (Cory, 2026-06-06):** confirm the real cost of 6 agents running 24/7, and prove the
employee-scaled monthly covers it at **≥75% margin on token cost** — so a 250-employee firm can
never sign the $8k install and bleed us dry monthly.

**Answer: yes — the customer-friendly ladder still clears a 50–75% margin on token cost at every tier.**
(Re-tiered 2026-06-06 at Cory's direction: lower, less-intimidating monthly — 50–75% band, not the old 78%+.)

---

## 1. "24/7" does NOT mean 24/7 token burn

The agents are **event-driven and serverless**, not a always-on loop:

- Each agent makes **one** `client.messages.create` call *only when it actually produces a
  recommendation* (`app/agents/*/reasoning.py`, `max_tokens=1200`, persona prompt-cached). There is
  **no `while True` / polling loop** anywhere in `app/`.
- **Cloud Run scales to zero.** When nobody is using the system, compute cost ≈ **$0**. We pay per
  request, not per hour.
- The only *scheduled* spend is the **nightly learning consolidation** (one cron/night/tenant —
  `POST /v1/learning/cron/consolidate`), which makes a handful of small (`max_tokens=300`) calls.

So "6 agents 24/7" = **6 agents available 24/7, billed ~2¢ only when one does work.** The Booking
agent answering a 9pm call costs ~2¢ *and books revenue* — cost scales with value, not with clock time.

## 2. Cost per run (one agent recommendation)

| Model | Input ~1,200 tok | Output ~800 tok | Embedding | **Per run** |
|---|---|---|---|---|
| `claude-sonnet-4-6` ($3 / $15 per 1M) | $0.0036 | $0.0120 | ~$0.0001 | **~$0.016** |
| `claude-haiku-4-5` ($1 / $5 per 1M) | $0.0012 | $0.0040 | ~$0.0001 | **~$0.006** |

Persona is sent with `cache_control: ephemeral` → cached input is ~90% cheaper on repeat, so these
are upper bounds. **Planning number: $0.02/run (Sonnet), $0.008/run (Haiku).**

## 3. Fixed per-tenant cost

- **Nightly learning:** ~$0.10–0.30/tenant/night → **~$6/tenant/mo** (budget $10).
- **Infra:** Cloud Run scale-to-zero (~$0 idle) + one shared Supabase ($10/mo across *all* tenants) +
  Secret Manager (pennies). Effectively **~$1/tenant/mo** at any real tenant count.

## 4. Usage model (deliberately heavy, so we never under-price)

Cost scales with **active users** (people who actually open the Command Center / trigger agents —
not every employee on payroll). Safe-heavy assumption: **40 agent runs / active user / workday** →
880 runs/user/mo.

| Narration model | $/run | $/active user/mo (heavy) |
|---|---|---|
| All Sonnet | $0.02 | ~$17.6 |
| Blended (4 high-freq agents on Haiku, 2 on Sonnet) | ~$0.011 | **~$10** |
| All Haiku | $0.008 | ~$7 |

**Planning number: $10 / active user / mo** (blended, heavy). Real-world will be lower (techs on the
mobile app are light users; prompt caching cuts input).

## 5. The monthly ladder (customer-friendly: 50–75% margin band)

Priced so the monthly is **not scary** while still clearing a **50–75% margin on token cost**. Tiers by
people actually using the system (modeled typical → safe-heavy: ~$6 → $10/user + $10/tenant nightly):

| People using the system | Monthly | Token COGS (typical → heavy) | **Margin on token cost** |
|---|---|---|---|
| Up to 25 | **$500** | ~$135 → ~$260 | **~74% → ~48%** |
| 26–75 | **$1,500** | ~$385 → ~$760 | **~74% → ~49%** |
| 76–125 | **$3,000** | ~$635 → ~$1,260 | **~79% → ~58%** |
| 126–250 | **from $6,000** | ~$1,260 → ~$2,510 | **~79% → ~58%** |
| 250+ | custom | — | — |

Margins sit in the **50–75% band** across realistic usage (≈75% typical, ≈50% at the absolute all-heavy
edge). The **Haiku-routing lever** (§6) is the floor protector — narrating the high-frequency agents on
Haiku 4.5 pulls every tier back to 65–80% even at heavy use. Still far cheaper for big firms than the old
ladder (250 seats: **$6k, was $12k**) — deliberately less intimidating, still safely profitable. A 250-seat
firm pays **~$6k/mo, not $500.** Founding-25 buyers lock their **per-seat rate** for life.

> Note: the $8,000 install is a separate one-time fee (setup, integration, tuning). The 75% rule above
> is on the **monthly token cost** as asked. The gross-margin *dollars* ($500 − ~$110 = ~$390/mo on the
> smallest tier) also fund Cory's amortized maintenance time (~$150/hr) — kept low by amortizing product
> work across all tenants.

## 6. Headroom levers (if usage ever runs hotter than modeled)

1. **Model routing** — narrate the high-frequency, short-output agents (Booking, Routing, Documents)
   on **Haiku 4.5** (−60% per run). Already a one-line config per agent (`workforce_reasoning_model`
   → per-agent override). This alone pushes every tier to ≥85%.
2. **Per-seat included-runs allowance + overage** — e.g., 600 included runs/seat/mo, overage at cost
   +75%. Turns the *worst case* (one user hammering Sonnet 100×/day) into additional revenue, not loss.
3. **Prompt caching** (already on) + tighter `max_tokens` for the short agents.
4. **Batch / off-peak** the nightly consolidation (already off-peak at 2am MT).

## 7. Bottom line

- No idle burn; ~2¢ per recommendation; ~$10/active-user/mo at heavy use.
- The ladder holds a **50–75% margin on token cost at every tier** (typical → heavy), with Haiku routing as
  the floor — friendly enough that big firms aren't scared off, still safely profitable.
- Large firms pay proportionally (≤10 → $500 … 101–250 → from $12k), so the $8k install can never be
  followed by a runaway monthly loss.


## 8. Addendum 2026-06-09 — agents 7+8 (Email, SEO/GEO)
Email (daily briefing cron ~30 runs/mo) + SEO (weekly, ~4 heavier runs/mo) add ≈ **$1-3/tenant/mo** at
Sonnet rates — noise inside the existing $10/tenant fixed budget. Seat-ladder margins unchanged (50-75%
band holds). The value-stack benchmarks used on the site: Clutch 2026 avg SEO retainer $3,199/mo;
US 24/7 answering $400-2,500/mo; HVAC bookkeeping $3,500-5,000/mo (part-time admin $1,200-2,800);
blog content $150-600/post; inbox AI tools $30-50/user/mo.
