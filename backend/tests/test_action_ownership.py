"""Pure tests for action ownership (the authz anchor: a kind's OWNING agent, not the stored agent)."""
from __future__ import annotations

import pytest

from app.actions.ownership import KIND_OWNER, derive_owning_agent


@pytest.mark.parametrize("kind,owner", sorted(KIND_OWNER.items()))
def test_every_mapped_kind_resolves_to_its_owner_over_the_stored_agent(kind: str, owner: str):
    # Even when the proposer declared a DIFFERENT agent, the owner wins (the spoof-proofing).
    assert derive_owning_agent(kind, "some_other_declared_agent") == owner


def test_money_legal_pay_kind_is_owned_by_workforce_not_the_declared_agent():
    # The canonical escalation attempt: claim collections on a payroll write.
    assert derive_owning_agent("payroll_adjustment", "collections") == "workforce"


def test_unmapped_kind_falls_back_to_the_declared_agent():
    assert derive_owning_agent("some_unmapped_kind", "booking") == "booking"
