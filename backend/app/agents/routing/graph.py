"""The Routing agent as a LangGraph StateGraph: fetch -> analyze -> reason (thin nodes)."""
from __future__ import annotations

from datetime import date
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.agents.routing.analytics import RoutingAnalysis, analyze
from app.agents.routing.data import assemble_dispatch_data
from app.agents.routing.models import DispatchData
from app.agents.routing.reasoning import explain
from app.config import Settings
from app.integrations.dispatch.client import DispatchClient


class RoutingState(TypedDict, total=False):
    as_of: date
    settings: Settings
    client: DispatchClient
    lessons: str  # self-learning memory injected by the service (steers NARRATION only, not figures)
    provider: str  # tenant's field-service system display name (narration/metadata only, not figures)
    data: DispatchData
    analysis: RoutingAnalysis
    narrative: str
    reasoning_source: str


async def _fetch(state: RoutingState) -> dict:
    return {"data": await assemble_dispatch_data(state["client"], as_of=state["as_of"])}


async def _analyze(state: RoutingState) -> dict:
    return {"analysis": analyze(state["data"])}


async def _reason(state: RoutingState) -> dict:
    settings = state["settings"]
    source = "template" if (settings.disable_llm or not settings.anthropic_api_key) else "llm"
    narrative = await explain(
        state["analysis"],
        settings,
        lessons=state.get("lessons", ""),
        provider=state.get("provider", "ServiceTitan"),
    )
    return {"narrative": narrative, "reasoning_source": source}


def build_routing_graph():
    graph = StateGraph(RoutingState)
    graph.add_node("fetch", _fetch)
    graph.add_node("analyze", _analyze)
    graph.add_node("reason", _reason)
    graph.set_entry_point("fetch")
    graph.add_edge("fetch", "analyze")
    graph.add_edge("analyze", "reason")
    graph.add_edge("reason", END)
    return graph.compile()


ROUTING_GRAPH = build_routing_graph()
