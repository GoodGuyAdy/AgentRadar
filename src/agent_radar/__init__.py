"""AgentRadar Python SDK alias module for `agent-radar` package.

Enables both `import agent_radar` and `import agentradar`.
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
    init,
    shutdown,
    flush,
    agent,
    tool,
    __version__,
)
from agentradar import __all__  # noqa: F401
