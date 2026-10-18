"""Tests for AgentRadar OpenTelemetry auto-instrumentation and SDK integration."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

import agentradar
from agentradar.otel.decorators import agent, tool
from agentradar.otel.init import _reset_for_testing, flush, init, shutdown
from agentradar.otel.instrumentors import (
    _INSTRUMENTORS,
    _NAME_TO_ENTRY,
    _activate_instrumentor,
    auto_instrument,
    instrument_frameworks,
)
from agentradar.otel.processor import PayloadStrippingProcessor, _strip_span


@pytest.fixture(autouse=True)
def reset_otel_state():
    """Ensure clean global OTel state before and after each test."""
    _reset_for_testing()
    yield
    _reset_for_testing()


# ===========================================================================
# 1. Init & Idempotency Tests
# ===========================================================================


def test_init_idempotent():
    """Calling init() multiple times is safe and only sets up once."""
    with patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter") as mock_exp:
        init(api_key="ar_live_test_key_123", endpoint="http://localhost:8000")
        init(api_key="ar_live_test_key_123", endpoint="http://localhost:8000")
        init(api_key="ar_live_different_key", endpoint="http://localhost:8000")

        # Exporter should only have been created once
        assert mock_exp.call_count == 1


def test_init_disabled():
    """When enabled=False, init() does nothing."""
    with patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter") as mock_exp:
        init(api_key="ar_live_test_key_123", enabled=False)
        assert mock_exp.call_count == 0


def test_init_missing_api_key_raises_or_logs(monkeypatch):
    """When no API key is provided and none in env, init logs warning and gracefully returns."""
    for key in ["AGENTRADAR_API_KEY", "AR_API_KEY", "AGENT_RADAR_API_KEY"]:
        monkeypatch.delenv(key, raising=False)

    with patch("agentradar.otel.init.logger.warning") as mock_warn:
        init(api_key=None)
        assert mock_warn.called
        assert "OTel setup failed" in mock_warn.call_args[0][0]


def test_init_config_from_env(monkeypatch):
    """Configuration falls back to environment variables."""
    monkeypatch.setenv("AGENTRADAR_API_KEY", "ar_live_from_env")
    monkeypatch.setenv("AGENTRADAR_ENDPOINT", "https://custom.endpoint.in/")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "my-env-agent")

    with patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter") as mock_exp:
        init()
        assert mock_exp.call_count == 1
        _, kwargs = mock_exp.call_args
        assert kwargs["endpoint"] == "https://custom.endpoint.in/api/v1/traces"
        assert kwargs["headers"]["Authorization"] == "Bearer ar_live_from_env"


# ===========================================================================
# 2. Payload Stripping Processor Tests
# ===========================================================================


def test_payload_stripping_processor_removes_payloads():
    """PayloadStrippingProcessor removes prompt/completion/input/output attrs."""
    in_memory = InMemorySpanExporter()
    provider = TracerProvider()
    stripper = PayloadStrippingProcessor(SimpleSpanProcessor(in_memory))
    provider.add_span_processor(stripper)

    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("agent_step") as span:
        # Non-payload attributes
        span.set_attribute("openinference.span.kind", "AGENT")
        span.set_attribute("agent.name", "Assistant")
        span.set_attribute("llm.model_name", "gpt-4o")
        span.set_attribute("llm.token_count.total", 150)
        # Payload attributes (must be stripped)
        span.set_attribute("input.value", "Sensitive user prompt")
        span.set_attribute("output.value", "Sensitive completion output")
        span.set_attribute("llm.input_messages", "[{'role': 'user'}]")
        span.set_attribute("gen_ai.prompt", "Secret prompt")

    spans = in_memory.get_finished_spans()
    assert len(spans) == 1
    attrs = dict(spans[0].attributes)

    # Safe attributes kept
    assert attrs["openinference.span.kind"] == "AGENT"
    assert attrs["agent.name"] == "Assistant"
    assert attrs["llm.model_name"] == "gpt-4o"
    assert attrs["llm.token_count.total"] == 150

    # Payload attributes stripped
    assert "input.value" not in attrs
    assert "output.value" not in attrs
    assert "llm.input_messages" not in attrs
    assert "gen_ai.prompt" not in attrs


def test_payload_stripping_preserves_spans_when_payloads_included():
    """When include_payloads=True, BatchSpanProcessor is used without stripping."""
    with patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"):
        init(api_key="ar_live_key", include_payloads=True)
        init_mod = sys.modules["agentradar.otel.init"]
        assert not isinstance(init_mod._span_processor, PayloadStrippingProcessor)


# ===========================================================================
# 3. Auto-Instrumentation Detection Logic Tests
# ===========================================================================


def test_auto_instrument_detects_and_warns_missing_instrumentor():
    """When framework is present but instrumentor package is missing, log actionable pip message."""
    mock_provider = MagicMock()

    with patch("agentradar.otel.instrumentors._is_installed") as mock_is_installed, \
         patch("agentradar.otel.instrumentors.logger.warning") as mock_warn:

        # Simulate openai installed, but instrumentor import fails
        def side_effect(mod_name):
            return mod_name == "openai"

        mock_is_installed.side_effect = side_effect

        auto_instrument(mock_provider)

        assert mock_warn.called
        # Check that warning mentioned openai and the pip package
        found = False
        for call in mock_warn.call_args_list:
            formatted = call[0][0] % call[0][1:]
            if "agentradar-sdk[openai]" in formatted:
                found = True
                break
        assert found, f"Expected pip install message in logs, got: {mock_warn.call_args_list}"


def test_explicit_framework_instrumentation():
    """Specifying frameworks=['openai'] attempts to instrument only that framework."""
    mock_provider = MagicMock()

    with patch("agentradar.otel.instrumentors._is_installed") as mock_is_installed, \
         patch("agentradar.otel.instrumentors._activate_instrumentor") as mock_act:

        mock_is_installed.return_value = True

        instrument_frameworks(["openai"], mock_provider)

        assert mock_act.call_count == 1
        entry = mock_act.call_args[0][0]
        assert entry[0] == "openai"


# ===========================================================================
# 4. Decorators Tests (@agent and @tool)
# ===========================================================================


def test_agent_and_tool_decorators_sync():
    """Synchronous functions decorated with @agent and @tool generate correct OTel spans."""
    in_memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(in_memory))
    otel_trace.set_tracer_provider(provider)

    @tool("calculator")
    def add(a: int, b: int) -> int:
        return a + b

    @agent("MathAgent")
    def run_agent(x: int, y: int) -> int:
        return add(x, y)

    res = run_agent(2, 3)
    assert res == 5

    spans = in_memory.get_finished_spans()
    assert len(spans) == 2

    tool_span = next(s for s in spans if s.name == "calculator")
    agent_span = next(s for s in spans if s.name == "MathAgent")

    assert tool_span.attributes["openinference.span.kind"] == "TOOL"
    assert tool_span.attributes["tool.name"] == "calculator"
    assert tool_span.status.status_code == StatusCode.OK

    assert agent_span.attributes["openinference.span.kind"] == "AGENT"
    assert agent_span.attributes["agent.name"] == "MathAgent"
    assert agent_span.status.status_code == StatusCode.OK


@pytest.mark.asyncio
async def test_agent_and_tool_decorators_async():
    """Asynchronous coroutines decorated with @agent and @tool generate correct OTel spans."""
    in_memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(in_memory))
    otel_trace.set_tracer_provider(provider)

    @tool
    async def fetch_data(key: str) -> dict:
        await asyncio.sleep(0.01)
        return {"data": key}

    @agent
    async def async_agent(key: str) -> dict:
        return await fetch_data(key)

    res = await async_agent("user_123")
    assert res == {"data": "user_123"}

    spans = in_memory.get_finished_spans()
    assert len(spans) == 2

    names = {s.name for s in spans}
    assert "fetch_data" in names
    assert "async_agent" in names


def test_agent_decorator_records_exception():
    """Exceptions raised in decorated functions are recorded on the span and re-raised."""
    in_memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(in_memory))
    otel_trace.set_tracer_provider(provider)

    @agent("FailingAgent")
    def will_fail():
        raise RuntimeError("Something exploded")

    with pytest.raises(RuntimeError, match="Something exploded"):
        will_fail()

    spans = in_memory.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code == StatusCode.ERROR
    assert "Something exploded" in spans[0].status.description


# ===========================================================================
# 5. End-to-End Test: SDK Tracing to Backend TestClient
# ===========================================================================


def test_e2e_otel_sdk_to_backend(tmp_path):
    """E2E: Send OTel spans directly from the SDK to the backend /api/v1/traces endpoint."""
    test_db = tmp_path / "test_e2e_otel.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"

    # Import backend app & setup test client
    backend_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "AgentRadarPrivate", "AgentRadar-private", "backend")
    )
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    engine = None
    try:
        from app.core import config as _cfg_mod
        _cfg_mod.settings.database_url = f"sqlite:///{test_db}"
        _cfg_mod.settings.require_email_verification = False

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.db.database import Base, get_db
        from fastapi.testclient import TestClient
        from app.main import app

        engine = create_engine(f"sqlite:///{test_db}", connect_args={"check_same_thread": False})
        TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        def override_get_db():
            db = TestingSession()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        Base.metadata.create_all(bind=engine)
        client = TestClient(app)

        # 1. Setup user, project, API key
        reg = client.post("/api/v1/auth/register", json={"email": "e2e@agentradar.dev", "password": "Pass1234!", "name": "E2E Tester"})
        assert reg.status_code == 201
        login = client.post("/api/v1/auth/login", json={"email": "e2e@agentradar.dev", "password": "Pass1234!"})
        assert login.status_code == 200
        token = login.json()["access_token"]
        auth_h = {"Authorization": f"Bearer {token}"}

        proj = client.post("/api/v1/projects", json={"name": "OTel E2E Project"}, headers=auth_h)
        assert proj.status_code == 201
        project_id = proj.json()["id"]

        key_resp = client.post(f"/api/v1/projects/{project_id}/api-keys", json={"name": "OTel Key"}, headers=auth_h)
        assert key_resp.status_code == 201
        api_key = key_resp.json()["full_key"]

        # 2. Configure synthetic OTLP trace protobuf request
        from opentelemetry.proto.trace.v1 import trace_pb2
        from opentelemetry.proto.common.v1 import common_pb2
        from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
            ExportTraceServiceRequest,
            ExportTraceServiceResponse,
        )

        req = ExportTraceServiceRequest()
        rs = req.resource_spans.add()
        rs.resource.attributes.add(key="service.name", value=common_pb2.AnyValue(string_value="E2EAgent"))
        ss = rs.scope_spans.add()

        root_span = ss.spans.add()
        root_span.trace_id = bytes.fromhex("11112222333344445555666677778888")
        root_span.span_id = bytes.fromhex("aaaaaaaaaaaaaaaa")
        root_span.name = "E2EAgentRun"
        root_span.start_time_unix_nano = 1700000000000000000
        root_span.end_time_unix_nano = 1700000005000000000
        attr = root_span.attributes.add()
        attr.key = "openinference.span.kind"
        attr.value.string_value = "AGENT"

        child_span = ss.spans.add()
        child_span.trace_id = bytes.fromhex("11112222333344445555666677778888")
        child_span.span_id = bytes.fromhex("bbbbbbbbbbbbbbbb")
        child_span.parent_span_id = bytes.fromhex("aaaaaaaaaaaaaaaa")
        child_span.name = "web_search"
        child_span.start_time_unix_nano = 1700000001000000000
        child_span.end_time_unix_nano = 1700000003000000000
        attr2 = child_span.attributes.add()
        attr2.key = "openinference.span.kind"
        attr2.value.string_value = "TOOL"
        attr3 = child_span.attributes.add()
        attr3.key = "tool.name"
        attr3.value.string_value = "web_search"

        # Post to /api/v1/traces using Bearer auth
        resp = client.post(
            "/api/v1/traces",
            content=req.SerializeToString(),
            headers={
                "Content-Type": "application/x-protobuf",
                "Authorization": f"Bearer {api_key}",
            },
        )
        assert resp.status_code == 200, f"OTLP traces POST failed: {resp.text}"

        # Parse binary protobuf response
        proto_resp = ExportTraceServiceResponse()
        proto_resp.ParseFromString(resp.content)
        assert proto_resp.partial_success.rejected_spans == 0

        # Verify run and events were created in backend DB
        runs_resp = client.get(f"/api/v1/runs?project_id={project_id}", headers=auth_h)
        assert runs_resp.status_code == 200
        runs_data = runs_resp.json()
        assert len(runs_data["items"]) >= 1

        run_id = runs_data["items"][0]["id"]
        events_resp = client.get(f"/api/v1/runs/{run_id}/events?project_id={project_id}", headers=auth_h)
        assert events_resp.status_code == 200
        events = events_resp.json()
        assert len(events) == 2
        event_types = {e["event_type"] for e in events}
        assert "agent" in event_types
        assert "tool_call" in event_types

    finally:
        if engine is not None:
            engine.dispose()
        if os.path.exists(test_db):
            try:
                os.remove(test_db)
            except Exception:
                pass
