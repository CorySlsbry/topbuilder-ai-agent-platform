"""The Collections agent as a LangGraph StateGraph: fetch -> analyze -> reason (thin nodes).

Orchestration only — every real decision lives in an independently tested module (analytics.py). The
linear shape leaves an obvious seam to later insert a human-in-the-loop approval node before any
dunning send (ADR 0007).
"""
from __future__ import annotations

from datetime import date
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.agents.collections.analytics import CollectionsAnalysis, analyze
from app.agents.collections.data import assemble_collections_data
from app.agents.collections.models import CollectionsData
from app.agents.collections.reasoning import explain
from app.config import Settings
from app.integrations.collections.client import CollectionsClient


class CollectionsState(TypedDict, total=False):
    as_of: date
    settings: Settings
    client: CollectionsClient
    lessons: str  # self-learning memory injected by the service (steers NARRATION only)
    provider: str  # AR book of record display name (narration/metadata only, not figures)
    data: CollectionsData
    analysis: CollectionsAnalysis
    narrative: str
    reasoning_source: str


async def _fetch(state: CollectionsState) -> dict:
    return {"data": await assemble_collections_data(state["client"], as_of=state["as_of"])}


async def _analyze(state: CollectionsState) -> dict:
    return {"analysis": analyze(state["data"])}


async def _reason(state: CollectionsState) -> dict:
    settings = state["settings"]
    source = "template" if (settings.disable_llm or not settings.anthropic_api_key) else "llm"
    narrative = await explain(
        state["analysis"],
        settings,
        lessons=state.get("lessons", ""),
        provider=state.get("provider", "QuickBooks"),
    )
    return {"narrative": narrative, "reasoning_source": source}


def build_collections_graph():
    graph = StateGraph(CollectionsState)
    graph.add_node("fetch", _fetch)
    graph.add_node("analyze", _analyze)
    graph.add_node("reason", _reason)
    graph.set_entry_point("fetch")
    graph.add_edge("fetch", "analyze")
    graph.add_edge("analyze", "reason")
    graph.add_edge("reason", END)
    return graph.compile()


COLLECTIONS_GRAPH = build_collections_graph()
