# ADR 0005 — ServiceTitan integration via a swappable adapter

- **Status:** Accepted
- **Date:** 2026-06-02
- **Related:** [0003](0003-deterministic-analytics-llm-explains.md)

## Context

Live ServiceTitan credentials are not available during initial development, yet we want to build
and test the real agent pipeline now. We also want the option to support other field-service
platforms (Housecall Pro, Jobber) later without rewriting agents.

ServiceTitan's API uses OAuth2 client-credentials (a `client_id`/`client_secret` plus a per-tenant
`ST-App-Key` header), is tenant-scoped by an account id in the path, and is **read-heavy** for our
use case (schedules, jobs, timesheets, payroll).

## Decision

Define a narrow, typed **`ServiceTitanClient` protocol** expressing only what the agents need
(e.g. `get_technicians`, `get_appointments`, `get_timesheets`, `get_job_durations`,
`get_demand_index`). Provide two implementations:

- **`FixtureServiceTitanClient`** — loads realistic JSON fixtures. Default in this slice; powers
  local dev, tests, and demos with zero credentials.
- **`LiveServiceTitanClient`** — real OAuth2 client-credentials flow with token caching, the
  `ST-App-Key` header, retries/backoff, and pagination. Selected by `SERVICETITAN_MODE=live`.

Selection is config-driven (`SERVICETITAN_MODE`); agents depend only on the protocol, never on a
concrete client. Scopes requested are **read-only** — consistent with the advisory-only guardrail
(ADR 0003 context): the platform recommends, it does not mutate ServiceTitan.

## Consequences

- The full agent pipeline runs and is tested today against fixtures; flipping to live data is a
  config change plus credentials, not a code change.
- Supporting another FSM later means writing one new adapter behind the same protocol.
- Read-only scopes make "we never write back to your system" an architectural fact, not a promise.
