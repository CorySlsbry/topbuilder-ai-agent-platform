"""The Financial agent as a LangGraph StateGraph: fetch -> analyze -> reason (thin nodes)."""
from __future__ import annotations

from datetime import date
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.agents.financial.analytics import FinancialAnalysis, analyze
from app.agents.financial.data import assemble_financial_data
from app.agents.financial.models import FinancialData
from app.agents.financial.reasoning import explain
from app.config import Settings
from app.integrations.accounting.client import AccountingClient


class FinancialState(TypedDict, total=False):
    as_of: date
    settings: Settings
    client: AccountingClient
    lessons: str  # self-learning memory injected by the service (steers NARRATION only, not figures)
    provider: str  # tenant's field-service system display name (narration/metadata only, not figures)
    data: FinancialData
    analysis: FinancialAnalysis
    narrative: str
    reasoning_source: str


async def _fetch(state: FinancialState) -> dict:
    return {"data": await assemble_financial_data(state["client"], as_of=state["as_of"])}


async def _analyze(state: FinancialState) -> dict:
    return {"analysis": analyze(state["data"])}


async def _reason(state: FinancialState) -> dict:
    settings = state["settings"]
    source = "template" if (settings.disable_llm or not settings.anthropic_api_key) else "llm"
    narrative = await explain(
        state["analysis"],
        settings,
        lessons=state.get("lessons", ""),
        provider=state.get("provider", "ServiceTitan"),
    )
    return {"narrative": narrative, "reasoning_source": source}


def build_financial_graph():
    graph = StateGraph(FinancialState)
    graph.add_node("fetch", _fetch)
    graph.add_node("analyze", _analyze)
    graph.add_node("reason", _reason)
    graph.set_entry_point("fetch")
    graph.add_edge("fetch", "analyze")
    graph.add_edge("analyze", "reason")
    graph.add_edge("reason", END)
    return graph.compile()


FINANCIAL_GRAPH = build_financial_graph()
