"""The self-learning layer: agents improve from approve/edit/reject/undo feedback.

Design (ADR 0003 is the firewall): learning evolves ONLY which precedent is cited, how the
narration reads, and how confident/autonomous an agent is — it never touches the deterministic
numbers. A case-based-reasoning memory (every run = a case, every feedback = its outcome label)
is retrieved into the *narration prompt only*; numeric thresholds live in a separately-gated param
store. See `scoring` (pure math), `app.repositories.memory` (persistence), `service` (orchestration).
"""
