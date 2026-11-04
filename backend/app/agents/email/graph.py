"""The Email agent as a LangGraph StateGraph: fetch -> analyze -> reason (thin nodes)."""
from __future__ import annotations

from datetime import date
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.agents.email.analytics import EmailAnalysis, analyze
from app.agents.email.data import assemble_inbox_data
from app.agents.email.models import InboxData
from app.agents.email.reasoning import explain, polish_drafts
from app.config import Settings
from app.integrations.email_inbox.client import EmailInboxClient


class EmailState(TypedDict, total=False):
    as_of: date
    settings: Settings
    client: EmailInboxClient
    lessons: str  # self-learning memory injected by the service (steers NARRATION only, not figures)
    provider: str  # tenant's field-service system display name (narration/metadata only, not figures)
    data: InboxData
    analysis: EmailAnalysis
    narrative: str
    polished: dict  # optional LLM wording overrides for reply drafts ({} in fixture/DISABLE_LLM mode)
    reasoning_source: str


async def _fetch(state: EmailState) -> dict:
    return {"data": await assemble_inbox_data(state["client"], as_of=state["as_of"])}


async def _analyze(state: EmailState) -> dict:
    return {"analysis": analyze(state["data"])}


async def _reason(state: EmailState) -> dict:
    settings = state["settings"]
    source = "template" if (settings.disable_llm or not settings.anthropic_api_key) else "llm"
    provider = state.get("provider", "ServiceTitan")
    narrative = await explain(
        state["analysis"], settings, lessons=state.get("lessons", ""), provider=provider
    )
    polished = await polish_drafts(state["analysis"], settings, provider=provider)
    return {"narrative": narrative, "polished": polished, "reasoning_source": source}


def build_email_graph():
    graph = StateGraph(EmailState)
    graph.add_node("fetch", _fetch)
    graph.add_node("analyze", _analyze)
    graph.add_node("reason", _reason)
    graph.set_entry_point("fetch")
    graph.add_edge("fetch", "analyze")
    graph.add_edge("analyze", "reason")
    graph.add_edge("reason", END)
    return graph.compile()


EMAIL_GRAPH = build_email_graph()
