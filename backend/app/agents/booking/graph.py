"""The Booking agent as a LangGraph StateGraph: fetch -> analyze -> reason (thin nodes).

The graph is orchestration only — every real decision lives in an independently tested module. The
linear shape leaves an obvious seam to later insert a human-in-the-loop approval node before any
ServiceTitan write-back (ADR 0006).
"""
from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.agents.booking.analytics import BookingAnalysis, analyze
from app.agents.booking.data import assemble_booking_data
from app.agents.booking.models import BookingData
from app.agents.booking.reasoning import explain
from app.config import Settings
from app.integrations.booking_intake.client import BookingIntakeClient


class BookingState(TypedDict, total=False):
    as_of: datetime
    settings: Settings
    client: BookingIntakeClient
    lessons: str  # self-learning memory injected by the service (steers NARRATION only, not figures)
    provider: str  # tenant's field-service system display name (narration/metadata only, not figures)
    data: BookingData
    analysis: BookingAnalysis
    narrative: str
    reasoning_source: str


async def _fetch(state: BookingState) -> dict:
    return {"data": await assemble_booking_data(state["client"], as_of=state["as_of"])}


async def _analyze(state: BookingState) -> dict:
    return {"analysis": analyze(state["data"])}


async def _reason(state: BookingState) -> dict:
    settings = state["settings"]
    source = "template" if (settings.disable_llm or not settings.anthropic_api_key) else "llm"
    narrative = await explain(
        state["analysis"],
        settings,
        lessons=state.get("lessons", ""),
        provider=state.get("provider", "ServiceTitan"),
    )
    return {"narrative": narrative, "reasoning_source": source}


def build_booking_graph():
    graph = StateGraph(BookingState)
    graph.add_node("fetch", _fetch)
    graph.add_node("analyze", _analyze)
    graph.add_node("reason", _reason)
    graph.set_entry_point("fetch")
    graph.add_edge("fetch", "analyze")
    graph.add_edge("analyze", "reason")
    graph.add_edge("reason", END)
    return graph.compile()


BOOKING_GRAPH = build_booking_graph()
