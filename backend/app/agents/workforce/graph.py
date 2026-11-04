"""The Workforce agent as a LangGraph StateGraph: fetch -> analyze -> reason.

Nodes are deliberately thin — every piece of real logic lives in an independently tested module
(data, analytics, reasoning). The graph is orchestration only, which keeps it easy to extend later
(e.g. inserting a human-in-the-loop approval node before any future write-back action).
"""
from __future__ import annotations

from datetime import date
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.agents.workforce.analytics import WorkforceAnalysis, analyze
from app.agents.workforce.data import assemble_workforce_data
from app.agents.workforce.models import WorkforceData
from app.agents.workforce.reasoning import explain
from app.config import Settings
from app.integrations.servicetitan.client import ServiceTitanClient


class WorkforceState(TypedDict, total=False):
    # inputs / dependencies
    as_of: date
    horizon_days: int
    settings: Settings
    client: ServiceTitanClient
    lessons: str  # self-learning memory injected by the service (steers NARRATION only, not figures)
    provider: str  # tenant's field-service system display name (narration/metadata only, not figures)
    # produced by nodes
    data: WorkforceData
    analysis: WorkforceAnalysis
    narrative: str
    reasoning_source: str  # 'llm' | 'template'


async def _fetch(state: WorkforceState) -> dict:
    data = await assemble_workforce_data(
        state["client"], as_of=state["as_of"], horizon_days=state["horizon_days"]
    )
    return {"data": data}


async def _analyze(state: WorkforceState) -> dict:
    return {"analysis": analyze(state["data"])}


async def _reason(state: WorkforceState) -> dict:
    settings = state["settings"]
    source = "template" if (settings.disable_llm or not settings.anthropic_api_key) else "llm"
    narrative = await explain(
        state["analysis"],
        settings,
        lessons=state.get("lessons", ""),
        provider=state.get("provider", "ServiceTitan"),
    )
    return {"narrative": narrative, "reasoning_source": source}


def build_workforce_graph():
    graph = StateGraph(WorkforceState)
    graph.add_node("fetch", _fetch)
    graph.add_node("analyze", _analyze)
    graph.add_node("reason", _reason)
    graph.set_entry_point("fetch")
    graph.add_edge("fetch", "analyze")
    graph.add_edge("analyze", "reason")
    graph.add_edge("reason", END)
    return graph.compile()


# Compiled once at import; safe to reuse across requests (state is per-invocation).
WORKFORCE_GRAPH = build_workforce_graph()
