"""The Inventory agent as a LangGraph StateGraph: fetch -> analyze -> reason (thin nodes)."""
from __future__ import annotations

from datetime import date
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.agents.inventory.analytics import InventoryAnalysis, analyze
from app.agents.inventory.data import assemble_inventory_data
from app.agents.inventory.models import InventoryData
from app.agents.inventory.reasoning import explain
from app.config import Settings
from app.integrations.inventory.client import InventoryClient


class InventoryState(TypedDict, total=False):
    as_of: date
    settings: Settings
    client: InventoryClient
    lessons: str  # self-learning memory injected by the service (steers NARRATION only, not figures)
    provider: str  # tenant's field-service system display name (narration/metadata only, not figures)
    data: InventoryData
    analysis: InventoryAnalysis
    narrative: str
    reasoning_source: str


async def _fetch(state: InventoryState) -> dict:
    return {"data": await assemble_inventory_data(state["client"], as_of=state["as_of"])}


async def _analyze(state: InventoryState) -> dict:
    return {"analysis": analyze(state["data"])}


async def _reason(state: InventoryState) -> dict:
    settings = state["settings"]
    source = "template" if (settings.disable_llm or not settings.anthropic_api_key) else "llm"
    narrative = await explain(
        state["analysis"],
        settings,
        lessons=state.get("lessons", ""),
        provider=state.get("provider", "ServiceTitan"),
    )
    return {"narrative": narrative, "reasoning_source": source}


def build_inventory_graph():
    graph = StateGraph(InventoryState)
    graph.add_node("fetch", _fetch)
    graph.add_node("analyze", _analyze)
    graph.add_node("reason", _reason)
    graph.set_entry_point("fetch")
    graph.add_edge("fetch", "analyze")
    graph.add_edge("analyze", "reason")
    graph.add_edge("reason", END)
    return graph.compile()


INVENTORY_GRAPH = build_inventory_graph()
