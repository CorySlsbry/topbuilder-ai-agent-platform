# ADR 0001 — Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-06-02

## Context

Top Builder AI targets a $10k–$50k+ enterprise price point. Buyers at that level run security and
architecture reviews. Decisions need a durable, reviewable trail — not tribal knowledge.

## Decision

We keep lightweight Architecture Decision Records (Michael Nygard format) in `docs/adr/`. Each ADR
is immutable once accepted; we supersede rather than edit. Numbering is sequential.

## Consequences

- A new engineer (or a prospect's security reviewer) can read `docs/adr/` and understand *why* the
  system looks the way it does.
- Reversing a decision means writing a new ADR that supersedes the old one, preserving history.
