"""AgentRadar Python SDK alias module for `agentradar-sdk` package.

Enables `import agentradar_sdk`, `import agentradar`, and `import agent_radar`.
"""

from agentradar import (  # noqa: F401
    AgentRadar,
    AsyncAgentRadar,
    AgentRun,
    AsyncAgentRun,
    EventType,
    RunStatus,
    AgentRadarError,
    AuthenticationError,
    APIError,
    ConfigurationError,
    NetworkError,
    IngestionResult,
    HealthStatus,
    RunSummary,
    RunDetail,
    EventDetail,
    AnalyticsSummary,
    __version__,
)
from agentradar import __all__  # noqa: F401
