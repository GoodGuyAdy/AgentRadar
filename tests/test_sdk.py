"""Tests for the AgentRadar Python SDK."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from agentradar import AgentRadar, AgentRun, EventType
from agentradar.config import Config
from agentradar.events import RunStatus, build_event
from agentradar.exceptions import APIError, AuthenticationError, ConfigurationError


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


def test_config_requires_api_key():
    with pytest.raises(ConfigurationError):
        Config(api_key="")


def test_config_strips_trailing_slash():
    c = Config(api_key="key", endpoint="http://localhost:8000/")
    assert c.endpoint == "http://localhost:8000"


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("AGENTRADAR_API_KEY", "env_key")
    monkeypatch.setenv("AGENTRADAR_ENDPOINT", "http://remote:9000")
    c = Config.from_env()
    assert c.api_key == "env_key"
    assert c.endpoint == "http://remote:9000"


# ---------------------------------------------------------------------------
# Event builder tests
# ---------------------------------------------------------------------------


def test_build_event_required_fields():
    evt = build_event(
        event_type=EventType.RUN_STARTED,
        run_id="run-1",
        agent_name="TestAgent",
    )
    assert evt["event_type"] == "run_started"
    assert evt["run_id"] == "run-1"
    assert evt["agent_name"] == "TestAgent"
    assert "event_id" in evt
    assert "timestamp" in evt


def test_build_event_strips_payloads_when_disabled():
    evt = build_event(
        event_type=EventType.TOOL_CALL,
        run_id="run-1",
        agent_name="TestAgent",
        input={"secret": "value"},
        output={"result": "data"},
        include_payloads=False,
    )
    assert "input" not in evt
    assert "output" not in evt


def test_build_event_includes_payloads_when_enabled():
    evt = build_event(
        event_type=EventType.TOOL_CALL,
        run_id="run-1",
        agent_name="TestAgent",
        input={"query": "hello"},
        include_payloads=True,
    )
    assert evt["input"] == {"query": "hello"}


def test_build_event_optional_fields():
    evt = build_event(
        event_type=EventType.LLM_CALL,
        run_id="run-1",
        agent_name="TestAgent",
        model_name="gpt-4o",
        provider="openai",
        token_usage={"prompt": 10, "completion": 20},
        duration_ms=250.5,
    )
    assert evt["model_name"] == "gpt-4o"
    assert evt["provider"] == "openai"
    assert evt["duration_ms"] == 250.5


# ---------------------------------------------------------------------------
# AgentRadar client + AgentRun tests
# ---------------------------------------------------------------------------


@respx.mock
def test_start_run_sends_events():
    route = respx.post("http://localhost:8000/api/v1/events/batch").mock(
        return_value=httpx.Response(200, json={"accepted": 2})
    )

    aw = AgentRadar(api_key="aw_test_key", endpoint="http://localhost:8000")
    with aw.start_run(agent_name="TestAgent") as run:
        run.log_tool_call(name="search", input={"q": "hello"})

    assert route.called
    payload = json.loads(route.calls[0].request.content)
    events = payload["events"]
    # run_started + tool_call + run_finished
    assert len(events) == 3
    types = [e["event_type"] for e in events]
    assert "run_started" in types
    assert "tool_call" in types
    assert "run_finished" in types


@respx.mock
def test_run_marks_failed_on_exception():
    respx.post("http://localhost:8000/api/v1/events/batch").mock(
        return_value=httpx.Response(200, json={"accepted": 3})
    )

    aw = AgentRadar(api_key="aw_test_key", endpoint="http://localhost:8000")
    with pytest.raises(ValueError):
        with aw.start_run(agent_name="TestAgent") as run:
            raise ValueError("boom")

    # The run should have been marked failed
    assert run.status == RunStatus.FAILED


@respx.mock
def test_authentication_error_on_401():
    respx.post("http://localhost:8000/api/v1/events/batch").mock(
        return_value=httpx.Response(401, json={"detail": "Unauthorized"})
    )

    aw = AgentRadar(api_key="bad_key", endpoint="http://localhost:8000")
    with pytest.raises(AuthenticationError):
        aw._send_batch([{"event_type": "run_started", "run_id": "x"}])


@respx.mock
def test_no_op_when_disabled():
    aw = AgentRadar(api_key="aw_key", endpoint="http://localhost:8000", enabled=False)
    with aw.start_run(agent_name="TestAgent") as run:
        run.log_tool_call(name="search")
    # No HTTP calls should have been made
    assert respx.calls.call_count == 0


@respx.mock
def test_batch_size_auto_flush():
    """Events exceeding batch_size should be auto-flushed."""
    calls = []

    def capture(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"accepted": 1})

    respx.post("http://localhost:8000/api/v1/events/batch").mock(side_effect=capture)

    aw = AgentRadar(
        api_key="aw_key",
        endpoint="http://localhost:8000",
        batch_size=3,
        include_payloads=True,
    )
    # Manually enqueue 4 events (should trigger auto-flush at >=3)
    for i in range(4):
        aw._enqueue(
            build_event(
                event_type=EventType.TOOL_CALL,
                run_id="run-1",
                agent_name="Agent",
                name=f"tool_{i}",
                include_payloads=True,
            )
        )
    aw.flush()
    total_events = sum(len(c["events"]) for c in calls)
    assert total_events == 4


def test_log_llm_call_helper():
    aw = AgentRadar(api_key="aw_key", endpoint="http://localhost:8000", enabled=False)
    run = AgentRun(client=aw, agent_name="Agent")
    # Should not raise even when disabled
    result = run.log_llm_call(
        model_name="gpt-4o",
        provider="openai",
        token_usage={"prompt": 10, "completion": 5},
    )
    # Disabled client — enqueue is a no-op but event_id is still returned
    # Actually for a regular AgentRun (not no-op), the event is enqueued
    # even when enabled=False on client (_enqueue returns early).
    # Just assert it returns a string.
    assert isinstance(result, str)


def test_context_manager_client():
    """AgentRadar itself can be used as a context manager."""
    with AgentRadar(api_key="aw_key", enabled=False) as aw:
        assert aw.config.enabled is False
