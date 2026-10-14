"""AgentWatch SDK configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


DEFAULT_ENDPOINT = "http://localhost:8000"
DEFAULT_TIMEOUT = 10.0  # seconds
DEFAULT_MAX_RETRIES = 3
DEFAULT_BATCH_SIZE = 50
SDK_VERSION = "0.1.0"


@dataclass
class Config:
    """SDK configuration container."""

    api_key: str
    endpoint: str = DEFAULT_ENDPOINT
    timeout: float = DEFAULT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES
    batch_size: int = DEFAULT_BATCH_SIZE
    enabled: bool = True  # set False to disable all telemetry
    include_payloads: bool = False  # if False, input/output content is stripped

    @classmethod
    def from_env(
        cls,
        api_key: str | None = None,
        endpoint: str | None = None,
        **kwargs: object,
    ) -> "Config":
        """Create a Config, falling back to environment variables."""
        resolved_key = api_key or os.environ.get("AGENTWATCH_API_KEY", "")
        resolved_endpoint = (
            endpoint
            or os.environ.get("AGENTWATCH_ENDPOINT", DEFAULT_ENDPOINT)
        )
        return cls(api_key=resolved_key, endpoint=resolved_endpoint, **kwargs)

    def __post_init__(self) -> None:
        from agentwatch.exceptions import ConfigurationError

        if not self.api_key:
            raise ConfigurationError(
                "api_key is required. Pass it explicitly or set the "
                "AGENTWATCH_API_KEY environment variable."
            )
        # Normalise endpoint — strip trailing slash
        self.endpoint = self.endpoint.rstrip("/")
