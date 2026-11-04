"""The Pricebook agent as a LangGraph StateGraph: fetch -> analyze -> reason (thin nodes).

Orchestration only — every real decision lives in an independently tested module (analytics.py). The
linear shape leaves an obvious seam to later insert a human-in-the-loop approval node before any
pricebook write (ADR 0007).
"""
from __future__ import annotations

from datetime import date
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.agents.pricebook.analytics import PricebookAnalysis, analyze
from app.agents.pricebook.data import assemble_pricebook_data
from app.agents.pricebook.models import PricebookData
from app.agents.pricebook.reasoning import explain
from app.config import Settings
from app.integrations.pricebook.client import PricebookClient


class PricebookState(TypedDict, total=False):
    as_of: date
    settings: Settings
    client: PricebookClient
    tolerance_pct: float
    lessons: str  # self-learning memory injected by the service (steers NARRATION only)
    data: PricebookData
    analysis: PricebookAnalysis
    narrative: str
    reasoning_source: str


async def _fetch(state: PricebookState) -> dict:
    return {
        "data": await assemble_pricebook_data(
            state["client"], as_of=state["as_of"], tolerance_pct=state.get("tolerance_pct", 5.0)
        )
    }


async def _analyze(state: PricebookState) -> dict:
    return {"analysis": analyze(state["data"])}


async def _reason(state: PricebookState) -> dict:
    settings = state["settings"]
    source = "template" if (settings.disable_llm or not settings.anthropic_api_key) else "llm"
    narrative = await explain(state["analysis"], settings, lessons=state.get("lessons", ""))
    return {"narrative": narrative, "reasoning_source": source}


def build_pricebook_graph():
    graph = StateGraph(PricebookState)
    graph.add_node("fetch", _fetch)
    graph.add_node("analyze", _analyze)
    graph.add_node("reason", _reason)
    graph.set_entry_point("fetch")
    graph.add_edge("fetch", "analyze")
    graph.add_edge("analyze", "reason")
    graph.add_edge("reason", END)
    return graph.compile()


PRICEBOOK_GRAPH = build_pricebook_graph()
