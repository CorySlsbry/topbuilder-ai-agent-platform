"""Unit tests for the assistant's inference-only Anthropic client posture (`assistant/llm_client.py`).

Pure: exercises only the header-building function, which is the externally-observable encoding of the
no-training / no-retention posture. No SDK import and no network — `build_assistant_client` itself just
threads these headers into the SDK constructor, which is covered by the SDK's own tests."""
from __future__ import annotations

from dataclasses import dataclass

from app.assistant.llm_client import (
    LLM_MAX_RETRIES,
    LLM_TIMEOUT_SECONDS,
    ZERO_RETENTION_HEADER,
    build_assistant_client,
    build_llm_client,
    inference_only_headers,
)
from app.config import Settings


@dataclass
class _StubSettings:
    """Minimal stand-in so the test asserts on the flag, not the full Settings object."""

    anthropic_zero_retention: bool = False


def test_inference_only_headers_are_empty_by_default() -> None:
    # Production default: no opt-in flag set -> the client is byte-for-byte the prior plain client.
    assert inference_only_headers(_StubSettings()) == {}


def test_inference_only_headers_emit_no_retention_only_when_opted_in() -> None:
    assert inference_only_headers(_StubSettings(anthropic_zero_retention=True)) == {
        ZERO_RETENTION_HEADER: "true"
    }


def test_no_header_ever_opts_into_training() -> None:
    # The whole point of the module: there is no setting and no header that turns training ON. Whatever
    # the flag, the emitted keys are a subset of the single no-retention opt-out header.
    on = inference_only_headers(_StubSettings(anthropic_zero_retention=True))
    off = inference_only_headers(_StubSettings(anthropic_zero_retention=False))
    assert set(on) <= {ZERO_RETENTION_HEADER}
    assert off == {}


def test_headers_tolerate_settings_without_the_flag() -> None:
    # The helper reads the flag defensively (getattr default False) so it works whether or not config.py
    # has been wired with the new field yet — an object with no such attribute must yield no headers.
    class _Bare:
        pass

    assert inference_only_headers(_Bare()) == {}


def test_build_llm_client_applies_timeout_and_retries() -> None:
    # The centralized client pins the network posture for EVERY LLM path. Assert the constructed SDK
    # client carries the 35s timeout and 2-retry budget (the whole reason the helper exists).
    client = build_llm_client(Settings(anthropic_api_key="sk-test-key"))
    assert client.timeout == LLM_TIMEOUT_SECONDS == 35.0
    assert client.max_retries == LLM_MAX_RETRIES == 2


def test_build_llm_client_sends_no_retention_header_only_when_opted_in() -> None:
    on = build_llm_client(Settings(anthropic_api_key="sk-test-key", anthropic_zero_retention=True))
    off = build_llm_client(Settings(anthropic_api_key="sk-test-key"))
    assert on.default_headers.get(ZERO_RETENTION_HEADER) == "true"
    assert ZERO_RETENTION_HEADER not in off.default_headers


def test_assistant_client_is_the_centralized_client() -> None:
    # The assistant's named constructor must be the same fully-configured client (not a plain one).
    assert build_assistant_client is build_llm_client
