"""AgentRadar Python SDK — AI agent observability."""

from agentradar.client import AgentRadar, AsyncAgentRadar
from agentradar.run import AgentRun, AsyncAgentRun
from agentradar.events import EventType, RunStatus
from agentradar.exceptions import (
    AgentRadarError,
    AuthenticationError,
    APIError,
    ConfigurationError,
    NetworkError,
)
from agentradar.models import (
    AnalyticsSummary,
    EventDetail,
    HealthStatus,
    IngestionResult,
    RunDetail,
    RunSummary,
)
from agentradar.otel.init import flush, init, shutdown
from agentradar.otel.decorators import agent, tool

__version__ = "0.1.0"
__all__ = [
    "AgentRadar",
    "AsyncAgentRadar",
    "AgentRun",
    "AsyncAgentRun",
    "EventType",
    "RunStatus",
    "AgentRadarError",
    "AuthenticationError",
    "APIError",
    "ConfigurationError",
    "NetworkError",
    "IngestionResult",
    "HealthStatus",
    "RunSummary",
    "RunDetail",
    "EventDetail",
    "AnalyticsSummary",
    "init",
    "shutdown",
    "flush",
    "agent",
    "tool",
]
