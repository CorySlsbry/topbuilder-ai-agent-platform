"""Go-live safety guarantee: with SERVICETITAN_MODE=live, the platform NEVER fabricates a write to the
customer's ServiceTitan — every write executor and live adapter fails closed until the real integration
is wired and verified against a real tenant. This is the load-bearing property that protects go-live.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.actions import executors as ex
from app.actions.executors import ActionError
from app.config import Settings
from app.integrations.dispatch.servicetitan_dispatch_client import ServiceTitanDispatchClient
from app.integrations.documents.servicetitan_documents_client import ServiceTitanDocumentsClient

LIVE = Settings(
    servicetitan_mode="live",
    actions_enabled=True,
    actions_allowed_kinds="book_appointment,file_document,request_signature,create_estimate",
)


class TestLiveWritesFailClosed:
    @pytest.mark.parametrize(
        "kind, params",
        [
            ("book_appointment", {"intake_id": "B01"}),
            ("file_document", {"doc_id": "DOC-1", "customer_ref": "C1"}),
            ("request_signature", {"doc_id": "DOC-1"}),
            ("create_estimate", {"job_ref": "JOB-1", "total_cents": 47248}),
        ],
    )
    async def test_write_executor_refuses_in_live_mode(self, kind: str, params: dict) -> None:
        # No real ServiceTitan write is wired yet -> the executor must REFUSE, never fake a success.
        with pytest.raises(ActionError):
            await ex.execute(kind, params, LIVE)


class TestLiveAdaptersFailClosed:
    async def test_dispatch_adapter_fails_closed(self) -> None:
        with pytest.raises(NotImplementedError):
            await ServiceTitanDispatchClient(LIVE).get_jobs(date.today())

    async def test_documents_adapter_fails_closed(self) -> None:
        with pytest.raises(NotImplementedError):
            await ServiceTitanDocumentsClient(LIVE).get_customers()
