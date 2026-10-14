"""AgentRadar Python SDK — AI agent observability."""

from agentradar.client import AgentRadar
from agentradar.run import AgentRun
from agentradar.events import EventType
from agentradar.exceptions import (
    AgentRadarError,
    AuthenticationError,
    APIError,
    ConfigurationError,
)

__version__ = "0.1.0"
__all__ = [
    "AgentRadar",
    "AgentRun",
    "EventType",
    "AgentRadarError",
    "AuthenticationError",
    "APIError",
    "ConfigurationError",
]
