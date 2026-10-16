"""AgentRadar event types and schema definitions."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


class EventType(str, Enum):
    RUN_STARTED = "run_started"
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    RUN_FINISHED = "run_finished"


class RunStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _ensure_dict(value: Any) -> dict[str, Any] | None:
    """Normalize input, output, or metadata to a dict compatible with FastAPI EventIn."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return value.model_dump()
    if hasattr(value, "dict") and callable(value.dict):
        return value.dict()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, (str, int, float, bool, list, tuple)):
        return {"value": value}
    try:
        return dict(value)
    except Exception:
        return {"value": str(value)}


def build_event(
    *,
    event_type: EventType | str,
    run_id: str,
    agent_name: str,
    name: str | None = None,
    duration_ms: float | None = None,
    input: Any = None,
    output: Any = None,
    error_type: str | None = None,
    error_message: str | None = None,
    model_name: str | None = None,
    provider: str | None = None,
    token_usage: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    timestamp: str | datetime | None = None,
    include_payloads: bool = True,
) -> dict[str, Any]:
    """Build a standardised event payload dict ready for the API."""
    # Normalise event_type to plain string
    et_value = event_type.value if isinstance(event_type, EventType) else str(event_type)

    # Normalise timestamp
    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        ts_value = timestamp.isoformat()
    elif isinstance(timestamp, str):
        ts_value = timestamp
    else:
        ts_value = _utcnow()

    event: dict[str, Any] = {
        "event_id": _new_id(),
        "run_id": run_id,
        "agent_name": agent_name,
        "event_type": et_value,
        "timestamp": ts_value,
    }

    if name is not None:
        event["name"] = name
    if duration_ms is not None:
        event["duration_ms"] = float(duration_ms)
    if error_type is not None:
        event["error_type"] = str(error_type)
    if error_message is not None:
        event["error_message"] = str(error_message)
    if model_name is not None:
        event["model_name"] = str(model_name)
    if provider is not None:
        event["provider"] = str(provider)
    if token_usage is not None:
        event["token_usage"] = _ensure_dict(token_usage)
    if metadata is not None:
        event["metadata"] = _ensure_dict(metadata)

    # Payload gating — strip sensitive data unless explicitly enabled
    if include_payloads:
        if input is not None:
            event["input"] = _ensure_dict(input)
        if output is not None:
            event["output"] = _ensure_dict(output)

    return event
