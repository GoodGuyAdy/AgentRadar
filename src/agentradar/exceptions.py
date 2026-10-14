"""AgentRadar SDK exceptions."""


class AgentRadarError(Exception):
    """Base exception for all AgentRadar SDK errors."""


class AuthenticationError(AgentRadarError):
    """Raised when the API key is invalid or missing."""


class APIError(AgentRadarError):
    """Raised when the AgentRadar API returns an error response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ConfigurationError(AgentRadarError):
    """Raised when the SDK is misconfigured."""


class NetworkError(AgentRadarError):
    """Raised on transient network failures after all retries are exhausted."""
