"""Universal event-detection -> auto-act layer (ADR 0010).

A change-feed poll loop (the completeness backbone) plus webhook overlays normalize every new/changed
ServiceTitan + QuickBooks item into the existing `event_queue`, then a drain worker routes each to the
owning deterministic agent and PROPOSES through the ADR-0007 action gate, advisory by default.

Pure, infra-free modules (`models`, `normalize`, `router`, `cursors`) are unit-testable in isolation;
`service` is the orchestration that touches the DB + the gate; `principal` mints the propose-only
system identity.
"""
