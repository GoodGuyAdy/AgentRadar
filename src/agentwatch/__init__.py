"""AgentWatch Python SDK — AI agent observability."""

from agentwatch.client import AgentWatch
from agentwatch.run import AgentRun
from agentwatch.events import EventType
from agentwatch.exceptions import (
    AgentWatchError,
    AuthenticationError,
    APIError,
    ConfigurationError,
)

__version__ = "0.1.0"
__all__ = [
    "AgentWatch",
    "AgentRun",
    "EventType",
    "AgentWatchError",
    "AuthenticationError",
    "APIError",
    "ConfigurationError",
]
