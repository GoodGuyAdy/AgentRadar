"""AgentRadar client — main entry point for the SDK."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

import httpx

from agentradar.config import Config, SDK_VERSION
from agentradar.exceptions import AuthenticationError, APIError, NetworkError
from agentradar.models import (
    AnalyticsSummary,
    EventDetail,
    HealthStatus,
    IngestionResult,
    RunDetail,
)
from agentradar.run import AgentRun, AsyncAgentRun

logger = logging.getLogger("agentradar")


class AgentRadar:
    """Main synchronous SDK client.

    Example::

        ar = AgentRadar(api_key="ar_live_...", endpoint="http://localhost:8000")

        with ar.start_run(agent_name="SupportAgent", input={"q": "hello"}) as run:
            run.log_tool_call(name="search", input={"query": "hello"})
            run.log_tool_result(name="search", output={"results": []})
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        endpoint: str | None = None,
        auth_token: str | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
        batch_size: int = 50,
        enabled: bool = True,
        include_payloads: bool = False,
    ) -> None:
        self.config = Config.from_env(
            api_key=api_key,
            endpoint=endpoint,
            auth_token=auth_token,
            timeout=timeout,
            max_retries=max_retries,
            batch_size=batch_size,
            enabled=enabled,
            include_payloads=include_payloads,
        )
        self._queue: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._http = httpx.Client(
            headers=self._get_headers(),
            timeout=self.config.timeout,
        )
        logger.debug("AgentRadar SDK initialised (endpoint=%s)", self.config.endpoint)

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "X-API-Key": self.config.api_key,
            "User-Agent": f"agentradar-python/{SDK_VERSION}",
            "Content-Type": "application/json",
        }
        if self.config.auth_token:
            headers["Authorization"] = f"Bearer {self.config.auth_token}"
        return headers

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

    def check_health(self) -> HealthStatus:
        """Check the health status of the AgentRadar platform backend."""
        url = f"{self.config.endpoint}/health"
        try:
            resp = self._http.get(url)
            resp.raise_for_status()
            return HealthStatus.from_dict(resp.json())
        except Exception as exc:
            raise APIError(f"Health check failed: {exc}") from exc

    def send_event(self, event: dict[str, Any]) -> IngestionResult:
        """Send a single event directly to the AgentRadar backend via POST /api/v1/events."""
        if not self.config.enabled:
            return IngestionResult(accepted=0, rejected=0)
        url = f"{self.config.endpoint}/api/v1/events"
        headers = self._get_headers()
        for attempt in range(1, self.config.max_retries + 1):
            try:
                resp = self._http.post(url, json=event, headers=headers)
                if resp.status_code == 401:
                    raise AuthenticationError(
                        "Invalid or missing API key. Check your AgentRadar API key."
                    )
                if resp.status_code == 422:
                    raise APIError(
                        f"Schema validation failed: {resp.text}",
                        status_code=422,
                    )
                if resp.status_code >= 500 and attempt < self.config.max_retries:
                    wait = 2 ** (attempt - 1)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json() if resp.content else {"accepted": 1, "rejected": 0, "errors": []}
                return IngestionResult.from_dict(data)
            except (AuthenticationError, APIError):
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500 and attempt < self.config.max_retries:
                    time.sleep(2 ** (attempt - 1))
                    continue
                raise APIError(str(exc), status_code=exc.response.status_code) from exc
            except httpx.TransportError as exc:
                if attempt == self.config.max_retries:
                    raise NetworkError(str(exc)) from exc
                time.sleep(2 ** (attempt - 1))
        return IngestionResult(accepted=0, rejected=1, errors=["Exhausted retries"])

    def flush(self) -> IngestionResult | None:
        """Send all buffered events to the backend immediately."""
        if not self.config.enabled:
            return None
        with self._lock:
            batch = self._queue[:]
            self._queue.clear()
        if batch:
            return self._send_batch(batch)
        return None

    def close(self) -> None:
        """Flush buffered events and close the HTTP session."""
        self.flush()
        self._http.close()

    # ------------------------------------------------------------------
    # Platform Query Helpers
    # ------------------------------------------------------------------

    def get_run(self, run_id: str, project_id: str) -> RunDetail:
        """Retrieve run details from the platform."""
        url = f"{self.config.endpoint}/api/v1/runs/{run_id}?project_id={project_id}"
        resp = self._http.get(url, headers=self._get_headers())
        resp.raise_for_status()
        return RunDetail.from_dict(resp.json())

    def get_run_events(self, run_id: str, project_id: str) -> list[EventDetail]:
        """Retrieve chronological events for a run."""
        url = f"{self.config.endpoint}/api/v1/runs/{run_id}/events?project_id={project_id}"
        resp = self._http.get(url, headers=self._get_headers())
        resp.raise_for_status()
        return [EventDetail.from_dict(e) for e in resp.json()]

    def get_analytics_summary(self, project_id: str, days: int = 30) -> AnalyticsSummary:
        """Retrieve analytics summary metrics for a project."""
        url = f"{self.config.endpoint}/api/v1/analytics/summary?project_id={project_id}&days={days}"
        resp = self._http.get(url, headers=self._get_headers())
        resp.raise_for_status()
        return AnalyticsSummary.from_dict(resp.json())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _enqueue(self, event: dict[str, Any]) -> None:
        if not self.config.enabled:
            return
        batch: list[dict[str, Any]] | None = None
        with self._lock:
            self._queue.append(event)
            if len(self._queue) >= self.config.batch_size:
                batch = self._queue[:]
                self._queue.clear()
        if batch:
            self._send_batch(batch)

    def _send_batch(self, events: list[dict[str, Any]]) -> IngestionResult:
        url = f"{self.config.endpoint}/api/v1/events/batch"
        headers = self._get_headers()
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
                if resp.status_code >= 500 and attempt < self.config.max_retries:
                    wait = 2 ** (attempt - 1)
                    logger.debug(
                        "Server error %d. Retrying in %ds (attempt %d)…",
                        resp.status_code,
                        wait,
                        attempt,
                    )
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json() if resp.content else {"accepted": len(events), "rejected": 0, "errors": []}
                result = IngestionResult.from_dict(data)
                if result.rejected > 0:
                    logger.warning(
                        "AgentRadar backend rejected %d event(s): %s",
                        result.rejected,
                        result.errors,
                    )
                logger.debug("Sent %d events (attempt %d)", len(events), attempt)
                return result
            except (AuthenticationError, APIError):
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500 and attempt < self.config.max_retries:
                    wait = 2 ** (attempt - 1)
                    time.sleep(wait)
                    continue
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
        return IngestionResult(accepted=0, rejected=len(events), errors=["Exhausted retries"])

    def __enter__(self) -> "AgentRadar":
        return self

    def __exit__(self, *_: Any) -> bool:
        self.close()
        return False


class AsyncAgentRadar:
    """Asynchronous AgentRadar client for asyncio-based agent architectures."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        endpoint: str | None = None,
        auth_token: str | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
        batch_size: int = 50,
        enabled: bool = True,
        include_payloads: bool = False,
    ) -> None:
        self.config = Config.from_env(
            api_key=api_key,
            endpoint=endpoint,
            auth_token=auth_token,
            timeout=timeout,
            max_retries=max_retries,
            batch_size=batch_size,
            enabled=enabled,
            include_payloads=include_payloads,
        )
        self._queue: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._http = httpx.AsyncClient(
            headers=self._get_headers(),
            timeout=self.config.timeout,
        )

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "X-API-Key": self.config.api_key,
            "User-Agent": f"agentradar-python/{SDK_VERSION}",
            "Content-Type": "application/json",
        }
        if self.config.auth_token:
            headers["Authorization"] = f"Bearer {self.config.auth_token}"
        return headers

    def start_run(
        self,
        agent_name: str,
        *,
        run_id: str | None = None,
        input: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncAgentRun:
        if not self.config.enabled:
            return _NoOpRun(client=self, agent_name=agent_name, run_id=run_id)  # type: ignore[return-value]
        return AsyncAgentRun(
            client=self,
            agent_name=agent_name,
            run_id=run_id,
            input=input,
            metadata=metadata,
        )

    def _enqueue(self, event: dict[str, Any]) -> None:
        if not self.config.enabled:
            return
        self._queue.append(event)
        # In async mode, auto-flush happens if batch_size reached and loop is running
        if len(self._queue) >= self.config.batch_size:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.flush())
            except RuntimeError:
                pass

    async def flush(self) -> IngestionResult | None:
        if not self.config.enabled:
            return None
        async with self._lock:
            batch = self._queue[:]
            self._queue.clear()
        if batch:
            return await self._send_batch(batch)
        return None

    async def _send_batch(self, events: list[dict[str, Any]]) -> IngestionResult:
        url = f"{self.config.endpoint}/api/v1/events/batch"
        headers = self._get_headers()
        payload = {"events": events}
        for attempt in range(1, self.config.max_retries + 1):
            try:
                resp = await self._http.post(url, json=payload, headers=headers)
                if resp.status_code == 401:
                    raise AuthenticationError("Invalid or missing API key.")
                if resp.status_code == 422:
                    raise APIError(f"Schema validation failed: {resp.text}", status_code=422)
                if resp.status_code >= 500 and attempt < self.config.max_retries:
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue
                resp.raise_for_status()
                data = resp.json() if resp.content else {"accepted": len(events), "rejected": 0, "errors": []}
                return IngestionResult.from_dict(data)
            except (AuthenticationError, APIError):
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500 and attempt < self.config.max_retries:
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue
                raise APIError(str(exc), status_code=exc.response.status_code) from exc
            except httpx.TransportError as exc:
                if attempt == self.config.max_retries:
                    raise NetworkError(str(exc)) from exc
                await asyncio.sleep(2 ** (attempt - 1))
        return IngestionResult(accepted=0, rejected=len(events), errors=["Exhausted retries"])

    async def check_health(self) -> HealthStatus:
        url = f"{self.config.endpoint}/health"
        try:
            resp = await self._http.get(url)
            resp.raise_for_status()
            return HealthStatus.from_dict(resp.json())
        except Exception as exc:
            raise APIError(f"Health check failed: {exc}") from exc

    async def close(self) -> None:
        await self.flush()
        await self._http.aclose()

    async def __aenter__(self) -> "AsyncAgentRadar":
        return self

    async def __aexit__(self, *_: Any) -> bool:
        await self.close()
        return False


class _NoOpRun(AgentRun):
    """No-op AgentRun used when telemetry is disabled."""

    def __enter__(self) -> "_NoOpRun":
        return self

    def __exit__(self, *_: Any) -> bool:
        return False

    async def __aenter__(self) -> "_NoOpRun":
        return self

    async def __aexit__(self, *_: Any) -> bool:
        return False

    def log_event(self, **kwargs: Any) -> str:  # type: ignore[override]
        return ""

    def start(self, **kwargs: Any) -> None:  # type: ignore[override]
        pass

    def finish(self, **kwargs: Any) -> None:  # type: ignore[override]
        pass

    def _start(self, **kwargs: Any) -> None:  # type: ignore[override]
        pass

    def _finish(self, **kwargs: Any) -> None:  # type: ignore[override]
        pass
