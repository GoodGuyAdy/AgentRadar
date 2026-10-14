"""AgentWatch SDK exceptions."""


class AgentWatchError(Exception):
    """Base exception for all AgentWatch SDK errors."""


class AuthenticationError(AgentWatchError):
    """Raised when the API key is invalid or missing."""


class APIError(AgentWatchError):
    """Raised when the AgentWatch API returns an error response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ConfigurationError(AgentWatchError):
    """Raised when the SDK is misconfigured."""


class NetworkError(AgentWatchError):
    """Raised on transient network failures after all retries are exhausted."""
