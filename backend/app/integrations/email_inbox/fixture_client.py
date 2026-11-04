"""Fixture-backed email-inbox client — a realistic unread contractor inbox + workflow stats.

26 emails engineered to a hand-computed oracle (asserted in tests/test_email_data.py so the demo
numbers can't silently drift): 7 needs_reply / 6 fyi / 9 trash / 4 workflow_report, topped by a
$12,400 commercial bid request; 3 workflows with exactly one ("Estimate follow-up") underperforming
its benchmarks. `age_hours` is stored relative, so the demo is always "this morning's inbox".
"""
from __future__ import annotations

import json
import pathlib
from datetime import date

from app.agents.email.models import EmailMessage, WorkflowStats

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


class FixtureEmailInboxClient:
    async def get_emails(self, as_of: date) -> list[EmailMessage]:
        return [EmailMessage(**row) for row in _load("inbox.json")]

    async def get_workflows(self) -> list[WorkflowStats]:
        return [WorkflowStats(**row) for row in _load("workflows.json")]
