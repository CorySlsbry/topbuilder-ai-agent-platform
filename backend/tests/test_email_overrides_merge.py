"""Operator-applied workflow copy overlays the email agent's run results — pure merge tests."""
from __future__ import annotations

from app.agents.email.schemas import AppliedRewriteOut, WorkflowOut
from app.agents.email.service import apply_overrides_to_result_dict


def _result_with(workflow_id: str) -> dict:
    return {
        "workflows": [
            {
                "workflow_id": workflow_id, "name": "Review Request", "emails_sent": 120,
                "open_rate": 0.2, "reply_rate": 0.05, "booked_jobs": 1,
                "benchmark_open_rate": 0.35, "benchmark_reply_rate": 0.12,
                "status": "underperforming", "proposed_rewrite": None,
            }
        ]
    }


OVERRIDE = {
    "workflow_id": "wf-1", "subject": "Quick question about your furnace",
    "preview": "Reply yes or no — 30 seconds.", "rationale": "",
    "updated_by": "person1@example.com", "updated_at": "2026-06-12T00:00:00+00:00",
}


def test_matching_override_lands_as_applied_rewrite():
    merged = apply_overrides_to_result_dict(_result_with("wf-1"), [OVERRIDE])
    applied = merged["workflows"][0]["applied_rewrite"]
    assert applied == {
        "subject": OVERRIDE["subject"], "preview": OVERRIDE["preview"],
        "applied_by": OVERRIDE["updated_by"], "applied_at": OVERRIDE["updated_at"],
    }
    # and the merged row still validates against the schema
    assert WorkflowOut.model_validate(merged["workflows"][0]).applied_rewrite is not None


def test_non_matching_override_leaves_workflow_untouched():
    merged = apply_overrides_to_result_dict(_result_with("wf-2"), [OVERRIDE])
    assert "applied_rewrite" not in merged["workflows"][0]


def test_no_overrides_is_a_no_op():
    data = _result_with("wf-1")
    assert apply_overrides_to_result_dict(data, []) is data


def test_applied_rewrite_schema_round_trip():
    out = AppliedRewriteOut(
        subject="s" * 3, preview="p" * 3, applied_by="person2@example.com", applied_at="2026-06-12",
    )
    assert out.subject and out.applied_by == "person2@example.com"
