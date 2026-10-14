"""AgentRadar client — main entry point for the SDK."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

from agentradar.config import Config, SDK_VERSION
from agentradar.exceptions import AuthenticationError, APIError, NetworkError
from agentradar.run import AgentRun

logger = logging.getLogger("agentradar")


class AgentRadar:
    """Main SDK client.

    Example::

        aw = AgentRadar(api_key="aw_live_...", endpoint="http://localhost:8000")

        with aw.start_run(agent_name="MyAgent", input={"q": "hello"}) as run:
            run.log_tool_call(name="search", input={"query": "hello"})
            run.log_tool_result(name="search", output={"results": []})
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        endpoint: str | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
        batch_size: int = 50,
        enabled: bool = True,
        include_payloads: bool = False,
    ) -> None:
        self.config = Config.from_env(
            api_key=api_key,
            endpoint=endpoint,
            timeout=timeout,
            max_retries=max_retries,
            batch_size=batch_size,
            enabled=enabled,
            include_payloads=include_payloads,
        )
        self._queue: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._http = httpx.Client(
            headers={
                "X-API-Key": self.config.api_key,
                "User-Agent": f"agentradar-python/{SDK_VERSION}",
                "Content-Type": "application/json",
            },
            timeout=self.config.timeout,
        )
        logger.debug("AgentRadar SDK initialised (endpoint=%s)", self.config.endpoint)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start_run(
        self,
        agent_name: str,
        *,
        run_id: str | None = None,
        input: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentRun:
        """Return an AgentRun context manager for tracking one agent run."""
        if not self.config.enabled:
            logger.debug("AgentRadar telemetry disabled — returning no-op run.")
            return _NoOpRun(client=self, agent_name=agent_name, run_id=run_id)
        return AgentRun(
            client=self,
            agent_name=agent_name,
            run_id=run_id,
            input=input,
            metadata=metadata,
        )

    def flush(self) -> None:
        """Send all buffered events to the backend immediately."""
        if not self.config.enabled:
            return
        with self._lock:
            batch = self._queue[:]
            self._queue.clear()
        if batch:
            self._send_batch(batch)

    def close(self) -> None:
        """Flush buffered events and close the HTTP session."""
        self.flush()
        self._http.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _enqueue(self, event: dict[str, Any]) -> None:
        if not self.config.enabled:
            return
        with self._lock:
            self._queue.append(event)
            if len(self._queue) >= self.config.batch_size:
                batch = self._queue[:]
                self._queue.clear()
        if len(self._queue) == 0 and batch:
            self._send_batch(batch)

    def _send_batch(self, events: list[dict[str, Any]]) -> None:
        url = f"{self.config.endpoint}/api/v1/events/batch"
        headers = {
            "X-API-Key": self.config.api_key,
            "User-Agent": f"agentradar-python/{SDK_VERSION}",
        }
        payload = {"events": events}
        for attempt in range(1, self.config.max_retries + 1):
            try:
                resp = self._http.post(url, json=payload, headers=headers)
                if resp.status_code == 401:
                    raise AuthenticationError(
                        "Invalid or missing API key. Check your AgentRadar API key."
                    )
                if resp.status_code == 422:
                    raise APIError(
                        f"Schema validation failed: {resp.text}",
                        status_code=422,
                    )
                resp.raise_for_status()
                logger.debug("Sent %d events (attempt %d)", len(events), attempt)
                return
            except (AuthenticationError, APIError):
                raise
            except httpx.HTTPStatusError as exc:
                raise APIError(str(exc), status_code=exc.response.status_code) from exc
            except httpx.TransportError as exc:
                if attempt == self.config.max_retries:
                    logger.warning(
                        "Failed to deliver %d events after %d attempts: %s",
                        len(events),
                        attempt,
                        exc,
                    )
                    raise NetworkError(str(exc)) from exc
                wait = 2 ** (attempt - 1)
                logger.debug("Retrying in %ds (attempt %d)…", wait, attempt)
                time.sleep(wait)

    def __enter__(self) -> "AgentRadar":
        return self

    def __exit__(self, *_: Any) -> bool:
        self.close()
        return False


class _NoOpRun(AgentRun):
    """No-op AgentRun used when telemetry is disabled."""

    def __enter__(self) -> "_NoOpRun":
        return self

    def __exit__(self, *_: Any) -> bool:
        return False

    def log_event(self, **kwargs: Any) -> str:  # type: ignore[override]
        return ""

    def _start(self, **kwargs: Any) -> None:  # type: ignore[override]
        pass

    def _finish(self, **kwargs: Any) -> None:  # type: ignore[override]
        pass
