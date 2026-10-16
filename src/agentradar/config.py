"""AgentRadar SDK configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_ENDPOINT = "https://api.agent-radar.in"
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
    auth_token: str | None = None  # optional Bearer JWT for platform API management

    @classmethod
    def from_env(
        cls,
        api_key: str | None = None,
        endpoint: str | None = None,
        auth_token: str | None = None,
        **kwargs: object,
    ) -> "Config":
        """Create a Config, falling back to environment variables."""
        resolved_key = (
            api_key
            or os.environ.get("AGENTRADAR_API_KEY")
            or os.environ.get("AR_API_KEY")
            or os.environ.get("AGENT_RADAR_API_KEY")
            or ""
        )
        resolved_endpoint = (
            endpoint
            or os.environ.get("AGENTRADAR_ENDPOINT")
            or os.environ.get("AR_ENDPOINT")
            or os.environ.get("AGENT_RADAR_ENDPOINT")
            or DEFAULT_ENDPOINT
        )
        resolved_token = (
            auth_token
            or os.environ.get("AGENTRADAR_AUTH_TOKEN")
            or os.environ.get("AR_AUTH_TOKEN")
            or None
        )
        return cls(
            api_key=resolved_key,
            endpoint=resolved_endpoint,
            auth_token=resolved_token,
            **kwargs,
        )

    def __post_init__(self) -> None:
        from agentradar.exceptions import ConfigurationError

        if not self.api_key:
            raise ConfigurationError(
                "api_key is required. Pass it explicitly or set the "
                "AGENTRADAR_API_KEY environment variable."
            )
        # Normalise endpoint — strip trailing slash
        self.endpoint = self.endpoint.rstrip("/")
