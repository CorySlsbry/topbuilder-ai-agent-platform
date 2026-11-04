"""The Documents agent as a LangGraph StateGraph: fetch -> analyze -> reason (thin nodes)."""
from __future__ import annotations

from datetime import date
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.agents.documents.analytics import DocumentsAnalysis, analyze
from app.agents.documents.ap import ApAnalysis
from app.agents.documents.ap import analyze as analyze_ap
from app.agents.documents.ap_models import VendorBillsData
from app.agents.documents.data import assemble_documents_data
from app.agents.documents.models import DocumentsData
from app.agents.documents.reasoning import explain
from app.agents.documents.warranty import WarrantyAnalysis
from app.agents.documents.warranty import analyze as analyze_warranty
from app.agents.documents.warranty_models import WarrantyData
from app.config import Settings
from app.integrations.documents.client import DocumentsClient


class DocumentsState(TypedDict, total=False):
    as_of: date
    settings: Settings
    client: DocumentsClient
    lessons: str  # self-learning memory injected by the service (steers NARRATION only, not figures)
    provider: str  # tenant's field-service system display name (narration/metadata only, not figures)
    data: DocumentsData
    analysis: DocumentsAnalysis
    ap_analysis: ApAnalysis  # Alex's PO/AP-from-email lane (A6)
    warranty_analysis: WarrantyAnalysis  # Alex's warranty-registration lane (A10)
    narrative: str
    reasoning_source: str


async def _fetch(state: DocumentsState) -> dict:
    return {"data": await assemble_documents_data(state["client"], as_of=state["as_of"])}


async def _analyze(state: DocumentsState) -> dict:
    data = state["data"]
    return {
        "analysis": analyze(data),
        "ap_analysis": analyze_ap(
            VendorBillsData(as_of=data.as_of, bills=data.vendor_bills, open_jobs=data.open_jobs)
        ),
        "warranty_analysis": analyze_warranty(
            WarrantyData(as_of=data.as_of, equipment=data.installed_equipment)
        ),
    }


async def _reason(state: DocumentsState) -> dict:
    settings = state["settings"]
    source = "template" if (settings.disable_llm or not settings.anthropic_api_key) else "llm"
    narrative = await explain(
        state["analysis"],
        settings,
        lessons=state.get("lessons", ""),
        provider=state.get("provider", "ServiceTitan"),
    )
    return {"narrative": narrative, "reasoning_source": source}


def build_documents_graph():
    graph = StateGraph(DocumentsState)
    graph.add_node("fetch", _fetch)
    graph.add_node("analyze", _analyze)
    graph.add_node("reason", _reason)
    graph.set_entry_point("fetch")
    graph.add_edge("fetch", "analyze")
    graph.add_edge("analyze", "reason")
    graph.add_edge("reason", END)
    return graph.compile()


DOCUMENTS_GRAPH = build_documents_graph()
