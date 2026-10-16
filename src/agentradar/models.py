"""AgentRadar data models and response schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class IngestionResult:
    """Result of event batch or single event ingestion."""

    accepted: int
    rejected: int = 0
    errors: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IngestionResult":
        return cls(
            accepted=data.get("accepted", 0),
            rejected=data.get("rejected", 0),
            errors=data.get("errors", []),
        )


@dataclass
class HealthStatus:
    """AgentRadar service health response."""

    status: str
    version: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HealthStatus":
        return cls(
            status=data.get("status", "unknown"),
            version=data.get("version", ""),
        )


@dataclass
class RunSummary:
    """Basic run information."""

    id: str
    project_id: str
    agent_name: str
    status: str
    event_count: int
    is_simulated: bool
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunSummary":
        return cls(
            id=data["id"],
            project_id=data["project_id"],
            agent_name=data["agent_name"],
            status=data["status"],
            event_count=data.get("event_count", 0),
            is_simulated=data.get("is_simulated", False),
            created_at=str(data.get("created_at", "")),
            started_at=str(data["started_at"]) if data.get("started_at") else None,
            finished_at=str(data["finished_at"]) if data.get("finished_at") else None,
            duration_ms=data.get("duration_ms"),
        )


@dataclass
class RunDetail(RunSummary):
    """Detailed run information including input and metadata."""

    input: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunDetail":
        return cls(
            id=data["id"],
            project_id=data["project_id"],
            agent_name=data["agent_name"],
            status=data["status"],
            event_count=data.get("event_count", 0),
            is_simulated=data.get("is_simulated", False),
            created_at=str(data.get("created_at", "")),
            started_at=str(data["started_at"]) if data.get("started_at") else None,
            finished_at=str(data["finished_at"]) if data.get("finished_at") else None,
            duration_ms=data.get("duration_ms"),
            input=data.get("input"),
            metadata=data.get("metadata") or data.get("metadata_"),
        )


@dataclass
class EventDetail:
    """Individual event in a run's timeline."""

    id: str
    run_id: str
    event_type: str
    timestamp: str
    name: str | None = None
    duration_ms: float | None = None
    error_type: str | None = None
    error_message: str | None = None
    model_name: str | None = None
    provider: str | None = None
    token_usage: dict[str, Any] | None = None
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventDetail":
        return cls(
            id=data["id"],
            run_id=data["run_id"],
            event_type=data["event_type"],
            timestamp=str(data.get("timestamp", "")),
            name=data.get("name"),
            duration_ms=data.get("duration_ms"),
            error_type=data.get("error_type"),
            error_message=data.get("error_message"),
            model_name=data.get("model_name"),
            provider=data.get("provider"),
            token_usage=data.get("token_usage"),
            input=data.get("input"),
            output=data.get("output"),
            metadata=data.get("metadata") or data.get("metadata_"),
        )


@dataclass
class AnalyticsSummary:
    """Aggregated analytics metrics."""

    total_runs: int
    successful_runs: int
    failed_runs: int
    running_runs: int
    error_rate: float
    avg_duration_ms: float | None
    total_tool_calls: int
    total_llm_calls: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnalyticsSummary":
        return cls(
            total_runs=data.get("total_runs", 0),
            successful_runs=data.get("successful_runs", 0),
            failed_runs=data.get("failed_runs", 0),
            running_runs=data.get("running_runs", 0),
            error_rate=float(data.get("error_rate", 0.0)),
            avg_duration_ms=data.get("avg_duration_ms"),
            total_tool_calls=data.get("total_tool_calls", 0),
            total_llm_calls=data.get("total_llm_calls", 0),
        )
