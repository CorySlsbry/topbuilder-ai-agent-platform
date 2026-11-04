"""Pure tests for authorize_approver — the per-employee approval gate (department + money/legal).

No DB: authorize_approver inspects only the principal's role/department and the action's kind/agent.
"""
from __future__ import annotations

import uuid

import pytest

from app.actions.service import ALWAYS_HITL_KINDS, ActionForbidden, authorize_approver
from app.security import Principal


def _principal(role: str, department: str | None) -> Principal:
    return Principal(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        email="person@example.com",
        role=role,
        aal="aal2",
        department=department,
        person_id=None,
    )


def _action(kind: str, agent: str) -> dict:
    return {"kind": kind, "agent": agent}


def test_department_lead_may_approve_an_action_owned_by_their_department():
    # create_ap_draft is owned by 'documents', which IS in finance's agents.
    authorize_approver(_principal("lead", "finance"), _action("create_ap_draft", "documents"))


def test_department_lead_is_refused_cross_department():
    # book_appointment is owned by 'booking', NOT in finance.
    with pytest.raises(ActionForbidden):
        authorize_approver(_principal("lead", "finance"), _action("book_appointment", "booking"))


def test_money_legal_requires_a_lead_not_a_plain_analyst():
    # A finance analyst clears the department check for 'documents' but NOT the money/legal lead rule.
    with pytest.raises(ActionForbidden, match="department-lead"):
        authorize_approver(_principal("analyst", "finance"), _action("create_ap_draft", "documents"))
    # The owning-department lead and the admin both pass.
    authorize_approver(_principal("lead", "finance"), _action("create_ap_draft", "documents"))
    authorize_approver(_principal("admin", None), _action("create_ap_draft", "documents"))


def test_non_money_legal_action_is_not_lead_gated_for_an_in_department_analyst():
    # file_document is owned by 'documents' (in finance) and is NOT an ALWAYS_HITL kind.
    assert "file_document" not in ALWAYS_HITL_KINDS
    authorize_approver(_principal("analyst", "finance"), _action("file_document", "documents"))


def test_owning_agent_beats_a_spoofed_stored_agent_on_a_pay_write():
    # A payroll write declared as agent='collections' is still Workforce-owned; a finance lead must be
    # refused on the DEPARTMENT check (workforce not in finance), never slipping through on the label.
    with pytest.raises(ActionForbidden):
        authorize_approver(_principal("lead", "finance"), _action("payroll_adjustment", "collections"))


def test_admin_is_unrestricted_across_departments():
    authorize_approver(_principal("admin", None), _action("payroll_adjustment", "workforce"))
    authorize_approver(_principal("admin", None), _action("ads.create_campaign", "ads"))


def test_ad_spend_is_operator_only_even_for_a_lead():
    # The 'ads' agent is in no department, so only an unrestricted admin can approve ad spend.
    with pytest.raises(ActionForbidden):
        authorize_approver(_principal("lead", "finance"), _action("ads.create_campaign", "ads"))
