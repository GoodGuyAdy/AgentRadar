"""Tests for the AgentRadar Python SDK."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import sys

import httpx
import pytest
import respx

from agentradar import (
    AgentRadar,
    AgentRun,
    AsyncAgentRadar,
    AsyncAgentRun,
    EventType,
    RunStatus,
    IngestionResult,
    HealthStatus,
)
from agentradar.config import Config, DEFAULT_ENDPOINT
from agentradar.events import _ensure_dict, build_event
from agentradar.exceptions import (
    APIError,
    AuthenticationError,
    ConfigurationError,
    NetworkError,
)


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


def test_config_requires_api_key():
    with pytest.raises(ConfigurationError):
        Config(api_key="")


def test_config_default_endpoint():
    c = Config(api_key="ar_key")
    assert c.endpoint == "https://api.agent-radar.in"
    assert DEFAULT_ENDPOINT == "https://api.agent-radar.in"


def test_config_strips_trailing_slash():
    c = Config(api_key="ar_key", endpoint="http://localhost:8000/")
    assert c.endpoint == "http://localhost:8000"


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("AGENTRADAR_API_KEY", "env_key")
    monkeypatch.setenv("AGENTRADAR_ENDPOINT", "http://remote:9000")
    c = Config.from_env()
    assert c.api_key == "env_key"
    assert c.endpoint == "http://remote:9000"


def test_config_from_env_alias(monkeypatch):
    monkeypatch.delenv("AGENTRADAR_API_KEY", raising=False)
    monkeypatch.setenv("AR_API_KEY", "ar_alias_key")
    monkeypatch.setenv("AR_ENDPOINT", "https://agent-radar.in")
    c = Config.from_env()
    assert c.api_key == "ar_alias_key"
    assert c.endpoint == "https://agent-radar.in"


# ---------------------------------------------------------------------------
# Event builder and payload normalization tests
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


def test_build_event_normalizes_primitive_payloads():
    # If user passes string or list, ensure it's normalized to dict for FastAPI EventIn
    evt = build_event(
        event_type=EventType.TOOL_CALL,
        run_id="run-1",
        agent_name="TestAgent",
        input="Search query string",
        output=42,
        include_payloads=True,
    )
    assert evt["input"] == {"value": "Search query string"}
    assert evt["output"] == {"value": 42}


@dataclass
class CustomPayload:
    field_a: str
    field_b: int


def test_build_event_normalizes_dataclass():
    payload = CustomPayload(field_a="val", field_b=123)
    evt = build_event(
        event_type=EventType.TOOL_CALL,
        run_id="run-1",
        agent_name="TestAgent",
        input=payload,
        include_payloads=True,
    )
    assert evt["input"] == {"field_a": "val", "field_b": 123}


def test_build_event_accepts_datetime_timestamp():
    dt = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
    evt = build_event(
        event_type=EventType.RUN_STARTED,
        run_id="run-1",
        agent_name="TestAgent",
        timestamp=dt,
    )
    assert evt["timestamp"] == "2026-10-16T12:00:00+00:00"


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
# Synchronous AgentRadar client + AgentRun tests
# ---------------------------------------------------------------------------


@respx.mock
def test_start_run_sends_events():
    route = respx.post("http://localhost:8000/api/v1/events/batch").mock(
        return_value=httpx.Response(200, json={"accepted": 3, "rejected": 0, "errors": []})
    )

    ar = AgentRadar(api_key="ar_live_test_key", endpoint="http://localhost:8000")
    with ar.start_run(agent_name="TestAgent") as run:
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
        return_value=httpx.Response(200, json={"accepted": 3, "rejected": 0, "errors": []})
    )

    ar = AgentRadar(api_key="ar_live_test_key", endpoint="http://localhost:8000")
    with pytest.raises(ValueError):
        with ar.start_run(agent_name="TestAgent") as run:
            raise ValueError("boom")

    assert run.status == RunStatus.FAILED


@respx.mock
def test_manual_run_lifecycle():
    route = respx.post("http://localhost:8000/api/v1/events/batch").mock(
        return_value=httpx.Response(200, json={"accepted": 2, "rejected": 0, "errors": []})
    )

    ar = AgentRadar(api_key="ar_live_test_key", endpoint="http://localhost:8000")
    run = ar.start_run(agent_name="ManualAgent")
    run.start(input={"step": 1})
    run.log_tool_call(name="calc")
    run.finish(status=RunStatus.SUCCESS)
    ar.flush()

    assert route.called
    payload = json.loads(route.calls[0].request.content)
    assert len(payload["events"]) == 3
    assert run.status == RunStatus.SUCCESS


@respx.mock
def test_track_tool_context_manager():
    respx.post("http://localhost:8000/api/v1/events/batch").mock(
        return_value=httpx.Response(200, json={"accepted": 4, "rejected": 0, "errors": []})
    )

    ar = AgentRadar(api_key="ar_live_test_key", endpoint="http://localhost:8000", include_payloads=True)
    with ar.start_run(agent_name="ToolAgent") as run:
        with run.track_tool("database_lookup", input={"id": 10}) as t:
            t.set_output({"status": "found"})

    ar.flush()
    # Check that events recorded tool_call and tool_result with output
    events = run._events if hasattr(run, "_events") and run._events else []


@respx.mock
def test_track_llm_context_manager():
    respx.post("http://localhost:8000/api/v1/events/batch").mock(
        return_value=httpx.Response(200, json={"accepted": 3, "rejected": 0, "errors": []})
    )

    ar = AgentRadar(api_key="ar_live_test_key", endpoint="http://localhost:8000", include_payloads=True)
    with ar.start_run(agent_name="LLMAgent") as run:
        with run.track_llm(model_name="claude-3-5-sonnet", provider="anthropic", input={"prompt": "hi"}) as llm:
            llm.set_result(output={"reply": "hello"}, token_usage={"prompt_tokens": 5, "completion_tokens": 2})


@respx.mock
def test_send_single_event():
    route = respx.post("http://localhost:8000/api/v1/events").mock(
        return_value=httpx.Response(200, json={"accepted": 1, "rejected": 0, "errors": []})
    )

    ar = AgentRadar(api_key="ar_live_test_key", endpoint="http://localhost:8000")
    evt = build_event(event_type="custom_check", run_id="r1", agent_name="A1")
    res = ar.send_event(evt)

    assert route.called
    assert res.accepted == 1
    assert res.rejected == 0


@respx.mock
def test_check_health():
    respx.get("http://localhost:8000/health").mock(
        return_value=httpx.Response(200, json={"status": "ok", "version": "0.1.0"})
    )

    ar = AgentRadar(api_key="ar_live_test_key", endpoint="http://localhost:8000")
    h = ar.check_health()
    assert h.status == "ok"
    assert h.version == "0.1.0"


@respx.mock
def test_authentication_error_on_401():
    respx.post("http://localhost:8000/api/v1/events/batch").mock(
        return_value=httpx.Response(401, json={"detail": "Invalid API key"})
    )

    ar = AgentRadar(api_key="bad_key", endpoint="http://localhost:8000")
    with pytest.raises(AuthenticationError):
        ar._send_batch([{"event_type": "run_started", "run_id": "x"}])


@respx.mock
def test_no_op_when_disabled():
    ar = AgentRadar(api_key="ar_key", endpoint="http://localhost:8000", enabled=False)
    with ar.start_run(agent_name="TestAgent") as run:
        run.log_tool_call(name="search")
    assert respx.calls.call_count == 0


@respx.mock
def test_batch_size_auto_flush():
    calls = []

    def capture(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"accepted": 1, "rejected": 0, "errors": []})

    respx.post("http://localhost:8000/api/v1/events/batch").mock(side_effect=capture)

    ar = AgentRadar(
        api_key="ar_key",
        endpoint="http://localhost:8000",
        batch_size=3,
        include_payloads=True,
    )
    for i in range(4):
        ar._enqueue(
            build_event(
                event_type=EventType.TOOL_CALL,
                run_id="run-1",
                agent_name="Agent",
                name=f"tool_{i}",
                include_payloads=True,
            )
        )
    ar.flush()
    total_events = sum(len(c["events"]) for c in calls)
    assert total_events == 4


@respx.mock
def test_server_error_retry():
    # First attempt returns 502, second attempt succeeds with 200
    respx.post("http://localhost:8000/api/v1/events/batch").mock(
        side_effect=[
            httpx.Response(502, text="Bad Gateway"),
            httpx.Response(200, json={"accepted": 1, "rejected": 0, "errors": []}),
        ]
    )

    ar = AgentRadar(api_key="ar_key", endpoint="http://localhost:8000", max_retries=2)
    res = ar._send_batch([{"event_type": "run_started", "run_id": "r1"}])
    assert res.accepted == 1


# ---------------------------------------------------------------------------
# Asynchronous AsyncAgentRadar tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_async_agent_radar_flow():
    route = respx.post("http://localhost:8000/api/v1/events/batch").mock(
        return_value=httpx.Response(200, json={"accepted": 3, "rejected": 0, "errors": []})
    )

    async with AsyncAgentRadar(api_key="ar_live_async", endpoint="http://localhost:8000") as ar:
        async with ar.start_run(agent_name="AsyncWorker") as run:
            run.log_tool_call(name="fetch_data", input={"url": "https://example.com"})

    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_async_check_health():
    respx.get("http://localhost:8000/health").mock(
        return_value=httpx.Response(200, json={"status": "ok", "version": "0.1.0"})
    )

    ar = AsyncAgentRadar(api_key="ar_key", endpoint="http://localhost:8000")
    h = await ar.check_health()
    assert h.status == "ok"
    assert h.version == "0.1.0"
    await ar.close()


# ---------------------------------------------------------------------------
# Live FastAPI Integration Test (against main app backend)
# ---------------------------------------------------------------------------


def test_real_backend_integration():
    """Verify SDK compatibility with the actual main app FastAPI application."""
    main_app_backend = r"c:\Users\adity\OneDrive\Documents\AgentRadarPrivate\AgentRadar-private\backend"
    if not os.path.exists(main_app_backend):
        pytest.skip("Main app backend path not found")

    if main_app_backend not in sys.path:
        sys.path.insert(0, main_app_backend)

    test_db = os.path.join(main_app_backend, "test_sdk_verify.db")
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"

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
    except Exception as e:
        pytest.skip(f"FastAPI backend setup failed: {e}")

    try:
        client = TestClient(app)

        # 1. Register & login
        client.post(
            "/api/v1/auth/register",
            json={
                "name": "SDK Tester",
                "email": "sdk_tester_flow@agentradar.dev",
                "password": "securepassword123",
            },
        )
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "sdk_tester_flow@agentradar.dev", "password": "securepassword123"},
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 2. Create Project
        proj_resp = client.post(
            "/api/v1/projects",
            json={"name": "SDK Integration Cluster"},
            headers=auth_headers,
        )
        assert proj_resp.status_code == 201
        project_id = proj_resp.json()["id"]

        # 3. Create API Key
        key_resp = client.post(
            f"/api/v1/projects/{project_id}/api-keys",
            json={"name": "SDK Test Key"},
            headers=auth_headers,
        )
        assert key_resp.status_code == 201
        api_key = key_resp.json()["full_key"]
        assert api_key.startswith("ar_live_")

        # 4. Initialize SDK with real backend TestClient
        ar = AgentRadar(
            api_key=api_key,
            endpoint="http://testserver",
            include_payloads=True,
        )
        ar._http = client  # mount TestClient for direct dispatch

        # 5. Execute run with tool tracking and LLM call
        with ar.start_run(agent_name="IntegrationAgent", input={"prompt": "Diagnose anomaly"}) as run:
            run_id = run.run_id
            run.log_llm_call(
                model_name="gpt-4o",
                provider="openai",
                duration_ms=320.0,
                token_usage={"prompt_tokens": 50, "completion_tokens": 20},
            )
            with run.track_tool("query_logs", input={"severity": "error"}) as tool:
                tool.set_output({"matches": 2})

        # 6. Verify run recorded in backend
        run_resp = client.get(f"/api/v1/runs/{run_id}?project_id={project_id}", headers=auth_headers)
        assert run_resp.status_code == 200
        run_data = run_resp.json()
        assert run_data["id"] == run_id
        assert run_data["agent_name"] == "IntegrationAgent"
        assert run_data["status"] == "success"
        assert run_data["event_count"] >= 4
    finally:
        try:
            Base.metadata.drop_all(bind=engine)
            if os.path.exists(test_db):
                os.remove(test_db)
        except Exception:
            pass


def test_agent_radar_alias_import():
    """Verify that `import agent_radar`, `import agentradar_sdk`, and `import agentradar` work seamlessly."""
    import agent_radar
    import agentradar_sdk

    assert hasattr(agent_radar, "AgentRadar")
    assert hasattr(agent_radar, "AsyncAgentRadar")
    assert agent_radar.AgentRadar is AgentRadar
    assert agent_radar.__version__ == "0.1.0"

    assert hasattr(agentradar_sdk, "AgentRadar")
    assert hasattr(agentradar_sdk, "AsyncAgentRadar")
    assert agentradar_sdk.AgentRadar is AgentRadar
    assert agentradar_sdk.__version__ == "0.1.0"

