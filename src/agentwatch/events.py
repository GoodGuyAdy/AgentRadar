"""AgentWatch event types and schema definitions."""

from __future__ import annotations

from enum import Enum
from typing import Any
import uuid
from datetime import datetime, timezone


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


def build_event(
    *,
    event_type: EventType | str,
    run_id: str,
    agent_name: str,
    name: str | None = None,
    duration_ms: float | None = None,
    input: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    model_name: str | None = None,
    provider: str | None = None,
    token_usage: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    timestamp: str | None = None,
    include_payloads: bool = True,
) -> dict[str, Any]:
    """Build a standardised event payload dict ready for the API."""
    # Normalise event_type to plain string regardless of whether caller passed
    # an EventType enum or a raw string value.
    et_value = event_type.value if isinstance(event_type, EventType) else str(event_type)
    event: dict[str, Any] = {
        "event_id": _new_id(),
        "run_id": run_id,
        "agent_name": agent_name,
        "event_type": et_value,
        "timestamp": timestamp or _utcnow(),
    }

    if name is not None:
        event["name"] = name
    if duration_ms is not None:
        event["duration_ms"] = duration_ms
    if error_type is not None:
        event["error_type"] = error_type
    if error_message is not None:
        event["error_message"] = error_message
    if model_name is not None:
        event["model_name"] = model_name
    if provider is not None:
        event["provider"] = provider
    if token_usage is not None:
        event["token_usage"] = token_usage
    if metadata is not None:
        event["metadata"] = metadata

    # Payload gating — strip sensitive data unless explicitly enabled
    if include_payloads:
        if input is not None:
            event["input"] = input
        if output is not None:
            event["output"] = output

    return event
