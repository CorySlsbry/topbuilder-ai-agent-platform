"""Assistant tool registry — pure tests: the closed tool set, the permission gate, input
validation, and history hygiene. The Anthropic loop itself is network and stays untested here;
everything that decides WHAT the assistant may do is exercised below."""
from __future__ import annotations

from app.assistant import tools


EXPECTED_TOOLS = {
    "get_agent_results", "list_communications", "list_tasks",
    "create_task", "list_email_workflows", "update_email_workflow",
}


def test_registry_is_the_closed_expected_set():
    assert {t["name"] for t in tools.TOOL_SPECS} == EXPECTED_TOOLS
    assert tools.ADMIN_TOOLS == {"update_email_workflow"}
    for t in tools.TOOL_SPECS:
        assert t["description"] and t["input_schema"]["type"] == "object"


def test_admin_tool_refused_for_non_admin_roles():
    for role in ("analyst", "viewer"):
        ok, reason = tools.can_call(role, None, "update_email_workflow")
        assert not ok and "operator" in reason
    ok, _ = tools.can_call("admin", None, "update_email_workflow")
    assert ok


def test_agent_results_respect_department_scope():
    # dispatcher: routing yes, financial no
    ok, _ = tools.can_call("analyst", "dispatch", "get_agent_results", agent="routing")
    assert ok
    ok, reason = tools.can_call("analyst", "dispatch", "get_agent_results", agent="financial")
    assert not ok and "department" in reason
    # unrestricted (owner/executive): all six org agents
    for agent in ("workforce", "financial", "inventory", "booking", "routing", "documents"):
        ok, _ = tools.can_call("analyst", None, "get_agent_results", agent=agent)
        assert ok, agent


def test_operator_layer_agents_mirror_the_route_bar():
    # email/seo routes are operator-only (require_admin) — the assistant holds the same bar.
    for agent in tools.OPERATOR_AGENTS:
        ok, reason = tools.can_call("analyst", None, "get_agent_results", agent=agent)
        assert not ok and "operator" in reason
        ok, _ = tools.can_call("admin", None, "get_agent_results", agent=agent)
        assert ok
        assert tools.needs_operator_2fa("get_agent_results", agent=agent)
    assert not tools.needs_operator_2fa("get_agent_results", agent="booking")


def test_email_workflows_are_operator_only():
    for role, dept in (("analyst", "dispatch"), ("analyst", None), ("viewer", None)):
        ok, _ = tools.can_call(role, dept, "list_email_workflows")
        assert not ok
    ok, _ = tools.can_call("admin", None, "list_email_workflows")
    assert ok
    assert tools.needs_operator_2fa("list_email_workflows")


def test_create_task_mirrors_the_runner_bar():
    ok, reason = tools.can_call("viewer", None, "create_task")
    assert not ok and "analyst or operator" in reason
    for role in ("analyst", "admin"):
        ok, _ = tools.can_call(role, None, "create_task")
        assert ok


def test_unknown_tool_and_agent_fail_closed():
    ok, _ = tools.can_call("admin", None, "drop_all_tables")
    assert not ok
    ok, _ = tools.can_call("admin", None, "get_agent_results", agent="not-an-agent")
    assert not ok


def test_validate_override_accepts_sane_input_and_trims():
    clean, err = tools.validate_override({
        "workflow_id": " wf-review-request ",
        "subject": "Quick question about your furnace",
        "preview": "Reply yes or no — 30 seconds.",
    })
    assert err is None
    assert clean == {
        "workflow_id": "wf-review-request",
        "subject": "Quick question about your furnace",
        "preview": "Reply yes or no — 30 seconds.",
        "rationale": "",
    }


def test_validate_override_rejects_bad_input():
    assert tools.validate_override({"workflow_id": "", "subject": "ok subject", "preview": "ok preview"})[1]
    assert tools.validate_override({"workflow_id": "wf", "subject": "ab", "preview": "ok preview"})[1]
    assert tools.validate_override({"workflow_id": "wf", "subject": "ok subject", "preview": "x" * 201})[1]
    assert tools.validate_override(
        {"workflow_id": "wf", "subject": "ok subject", "preview": "ok preview", "rationale": "r" * 501}
    )[1]


def test_validate_task():
    clean, err = tools.validate_task({"title": "Call the supplier back", "department": "front_office"})
    assert err is None and clean["priority"] == 5 and clean["detail"] is None
    assert tools.validate_task({"title": "ab", "department": "front_office"})[1]
    # an unknown department is rejected ('skunkworks' is in no DEPT_AGENTS entry; 'marketing' is now a
    # real operator department after ADR 0009, so it would no longer be unknown).
    assert tools.validate_task({"title": "Valid title", "department": "skunkworks"})[1]
    assert tools.validate_task({"title": "Valid title", "department": "finance", "priority": 11})[1]


def test_sanitize_history_clips_filters_and_bounds_with_user_turns():
    raw = [
        {"role": "assistant", "content": "leading assistant turn is dropped"},
        {"role": "system", "content": "bad role dropped"},
        {"role": "user", "content": ""},
        {"role": "user", "content": "x" * 5000},
        {"role": "assistant", "content": "mid-conversation assistant turn survives"},
        {"role": "user", "content": "latest question"},
    ]
    out = tools.sanitize_history(raw, max_messages=12, max_chars=4000)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert len(out[0]["content"]) == 4000


def test_sanitize_history_keeps_only_the_last_n():
    raw = [{"role": "user", "content": f"m{i}"} for i in range(30)]
    out = tools.sanitize_history(raw, max_messages=12)
    assert len(out) == 12 and out[-1]["content"] == "m29"


def test_sanitize_history_drops_trailing_assistant_prefill():
    raw = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "a trailing assistant turn would be a prefill"},
    ]
    out = tools.sanitize_history(raw)
    assert [m["role"] for m in out] == ["user"]
    assert tools.sanitize_history([{"role": "assistant", "content": "only assistant"}]) == []
