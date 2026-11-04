"""Shared narration call path for the deterministic agents (the reasoning-layer plumbing).

Each agent's `reasoning.explain()` builds the same three things — a SYSTEM_PERSONA, an authoritative
`_analysis_brief(...)` dict, and a deterministic `_template_narrative(...)` — and wants the same
behavior around the model call: use the ONE centralized client (timeout/retries/headers), capture
token usage for telemetry, and verify the result is figure-faithful (ADR 0003) before shipping it,
falling back to the template on drift OR any error. That common path lives here so it is written once.

`narrate()` is async (it calls the model) but everything it depends on for SAFETY — the figure guard
and the template — is pure, so the only way it can return non-deterministic text is when the model
output passed the figure check. Telemetry is recorded into the per-task collector (see `_telemetry`);
a drift is logged as a structured `narration_figure_drift` event and the template ships instead.
"""
from __future__ import annotations

import logging
from typing import Any

from app.agents import _figure_guard, _telemetry
from app.config import Settings

logger = logging.getLogger("app.agents.narration")


def _text_of(response: Any) -> str:
    """Join the text blocks of an Anthropic response (ignores tool/other blocks)."""
    return "\n".join(
        b.text for b in getattr(response, "content", []) if getattr(b, "type", "") == "text"
    ).strip()


async def narrate(
    *,
    agent: str,
    settings: Settings,
    system: list[dict] | str,
    user_content: str,
    brief: Any,
    template: str,
    max_tokens: int = 1200,
    required_amounts: set[str] | None = None,
) -> str:
    """Run the narration model call with telemetry + the figure-faithfulness guard, or fall back.

    Returns the prose to ship. Order of guarantees:
      * `DISABLE_LLM` / no key            -> the deterministic `template`, unchanged (no call, no cost).
      * model error / empty completion    -> the `template` (narration must never break the pipeline).
      * model output drifts on figures    -> the `template`, plus a logged `narration_figure_drift`.
      * model output is figure-faithful   -> the model's prose.

    `brief` is the authoritative `_analysis_brief(...)` dict; its dollar amounts define the allowed set
    the output is checked against. `required_amounts`, when given, are the amounts that MUST appear
    (defaults to "every allowed amount that the template itself prints", so a legitimately terse model
    summary is not rejected for omitting a figure the template also omits).
    """
    if settings.disable_llm or not settings.anthropic_api_key:
        return template
    try:
        from app.assistant.llm_client import build_llm_client

        client = build_llm_client(settings)
        model = settings.workforce_reasoning_model
        system_param = system if isinstance(system, list) else [{"type": "text", "text": system}]
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_param,
            messages=[{"role": "user", "content": user_content}],
        )
        _telemetry.record_usage(model=model, usage=getattr(response, "usage", None))
        text = _text_of(response)
        if not text:
            return template
    except Exception:
        # Never let a narration failure break the (deterministic) pipeline.
        return template

    # `guard_or_fallback` defaults the required set to the template's own figures (so a terse-but-
    # faithful model summary is allowed; the model is only rejected for INVENTING or DROPPING a figure
    # the deterministic narrative also surfaces). Pass an explicit `required_amounts` to override.
    shipped, drift = _figure_guard.guard_or_fallback(
        narrative=text, template=template, brief=brief, required=required_amounts
    )
    if drift is not None:
        logger.warning(
            "narration_figure_drift",
            extra={"event": "narration_figure_drift", "agent": agent,
                   "invented": drift["invented"], "missing": drift["missing"]},
        )
    return shipped
