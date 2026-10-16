"""AgentRadar AgentRun — context manager and tracker for agent runs."""

from __future__ import annotations

from contextlib import contextmanager
import logging
import time
from typing import TYPE_CHECKING, Any, Generator

from agentradar.events import EventType, RunStatus, _new_id, build_event

if TYPE_CHECKING:
    from agentradar.client import AgentRadar, AsyncAgentRadar

logger = logging.getLogger("agentradar")


class ToolTracker:
    """Helper container to set tool outputs inside a track_tool context."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.output: Any = None

    def set_output(self, output: Any) -> None:
        self.output = output


class LLMTracker:
    """Helper container to set LLM outputs & token usage inside a track_llm context."""

    def __init__(self, model_name: str, provider: str | None = None) -> None:
        self.model_name = model_name
        self.provider = provider
        self.output: Any = None
        self.token_usage: dict[str, Any] | None = None

    def set_result(
        self,
        output: Any = None,
        token_usage: dict[str, Any] | None = None,
    ) -> None:
        self.output = output
        if token_usage is not None:
            self.token_usage = token_usage


class AgentRun:
    """Represents a single agent run.

    Use as a context manager for automatic start/finish tracking::

        with ar.start_run(agent_name="MyAgent") as run:
            run.log_event(event_type="tool_call", name="search")
    """

    def __init__(
        self,
        *,
        client: "AgentRadar",
        agent_name: str,
        run_id: str | None = None,
        input: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._client = client
        self.agent_name = agent_name
        self.run_id: str = run_id or _new_id()
        self._input = input
        self._metadata = metadata
        self._start_time: float | None = None
        self.status: RunStatus = RunStatus.RUNNING
        self._events: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "AgentRun":
        self.start(input=self._input, metadata=self._metadata)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        if exc_type is not None:
            self.log_event(
                event_type=EventType.ERROR,
                name=exc_type.__name__,
                error_type=exc_type.__name__,
                error_message=str(exc_val),
                metadata={"exception_class": exc_type.__qualname__},
            )
            self.finish(status=RunStatus.FAILED)
        else:
            self.finish(status=RunStatus.SUCCESS)
        self._client.flush()
        return False  # do not suppress the exception

    # ------------------------------------------------------------------
    # Explicit lifecycle API
    # ------------------------------------------------------------------

    def start(
        self,
        input: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Start the agent run and log the run_started event."""
        self._start_time = time.monotonic()
        self.log_event(
            event_type=EventType.RUN_STARTED,
            input=input or self._input,
            metadata=metadata or self._metadata,
        )

    def finish(
        self,
        status: RunStatus | str = RunStatus.SUCCESS,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Finish the agent run and log the run_finished event."""
        duration_ms: float | None = None
        if self._start_time is not None:
            duration_ms = (time.monotonic() - self._start_time) * 1000

        resolved_status = (
            status if isinstance(status, RunStatus) else RunStatus(str(status))
        )
        self.status = resolved_status

        meta: dict[str, Any] = {"status": resolved_status.value}
        if metadata:
            meta.update(metadata)

        self.log_event(
            event_type=EventType.RUN_FINISHED,
            duration_ms=duration_ms,
            metadata=meta,
        )

    # Backward-compatible internal aliases
    def _start(
        self,
        input: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.start(input=input, metadata=metadata)

    def _finish(self, status: RunStatus) -> None:
        self.finish(status=status)

    # ------------------------------------------------------------------
    # Public Logging API
    # ------------------------------------------------------------------

    def log_event(
        self,
        *,
        event_type: EventType | str,
        name: str | None = None,
        duration_ms: float | None = None,
        input: Any = None,
        output: Any = None,
        error_type: str | None = None,
        error_message: str | None = None,
        model_name: str | None = None,
        provider: str | None = None,
        token_usage: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp: Any = None,
    ) -> str:
        """Log an event on this run. Returns the generated event_id."""
        event = build_event(
            event_type=event_type,
            run_id=self.run_id,
            agent_name=self.agent_name,
            name=name,
            duration_ms=duration_ms,
            input=input,
            output=output,
            error_type=error_type,
            error_message=error_message,
            model_name=model_name,
            provider=provider,
            token_usage=token_usage,
            metadata=metadata,
            timestamp=timestamp,
            include_payloads=self._client.config.include_payloads,
        )
        self._client._enqueue(event)
        logger.debug(
            "Logged event type=%s run_id=%s name=%s",
            event_type,
            self.run_id,
            name,
        )
        return event["event_id"]

    # ------------------------------------------------------------------
    # LLM / Tool helpers
    # ------------------------------------------------------------------

    def log_llm_call(
        self,
        *,
        model_name: str,
        provider: str | None = None,
        input: Any = None,
        output: Any = None,
        duration_ms: float | None = None,
        token_usage: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return self.log_event(
            event_type=EventType.LLM_CALL,
            name=model_name,
            model_name=model_name,
            provider=provider,
            input=input,
            output=output,
            duration_ms=duration_ms,
            token_usage=token_usage,
            metadata=metadata,
        )

    def log_tool_call(
        self,
        *,
        name: str,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return self.log_event(
            event_type=EventType.TOOL_CALL,
            name=name,
            input=input,
            metadata=metadata,
        )

    def log_tool_result(
        self,
        *,
        name: str,
        output: Any = None,
        duration_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return self.log_event(
            event_type=EventType.TOOL_RESULT,
            name=name,
            output=output,
            duration_ms=duration_ms,
            metadata=metadata,
        )

    def log_error(
        self,
        *,
        error_type: str,
        error_message: str,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return self.log_event(
            event_type=EventType.ERROR,
            name=name,
            error_type=error_type,
            error_message=error_message,
            metadata=metadata,
        )

    def log_custom_event(
        self,
        *,
        name: str,
        event_type: str = "custom",
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        return self.log_event(
            event_type=event_type,
            name=name,
            metadata=metadata,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Context Trackers (Convenience instrumentation)
    # ------------------------------------------------------------------

    @contextmanager
    def track_tool(
        self,
        name: str,
        *,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> Generator[ToolTracker, None, None]:
        """Context manager to measure tool execution duration and log results or errors."""
        start_t = time.monotonic()
        self.log_tool_call(name=name, input=input, metadata=metadata)
        tracker = ToolTracker(name=name)
        try:
            yield tracker
        except Exception as exc:
            self.log_error(
                error_type=type(exc).__name__,
                error_message=str(exc),
                name=name,
                metadata=metadata,
            )
            raise
        else:
            dur_ms = (time.monotonic() - start_t) * 1000
            self.log_tool_result(
                name=name,
                output=tracker.output,
                duration_ms=dur_ms,
                metadata=metadata,
            )

    @contextmanager
    def track_llm(
        self,
        *,
        model_name: str,
        provider: str | None = None,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> Generator[LLMTracker, None, None]:
        """Context manager to measure LLM call duration and log results."""
        start_t = time.monotonic()
        tracker = LLMTracker(model_name=model_name, provider=provider)
        try:
            yield tracker
        except Exception as exc:
            self.log_error(
                error_type=type(exc).__name__,
                error_message=str(exc),
                name=model_name,
                metadata=metadata,
            )
            raise
        else:
            dur_ms = (time.monotonic() - start_t) * 1000
            self.log_llm_call(
                model_name=model_name,
                provider=provider,
                input=input,
                output=tracker.output,
                duration_ms=dur_ms,
                token_usage=tracker.token_usage,
                metadata=metadata,
            )


class AsyncAgentRun(AgentRun):
    """Asynchronous agent run tracker."""

    def __init__(
        self,
        *,
        client: "AsyncAgentRadar",
        agent_name: str,
        run_id: str | None = None,
        input: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        # Pass async client
        super().__init__(
            client=client,  # type: ignore[arg-type]
            agent_name=agent_name,
            run_id=run_id,
            input=input,
            metadata=metadata,
        )
        self._async_client = client

    async def __aenter__(self) -> "AsyncAgentRun":
        self.start(input=self._input, metadata=self._metadata)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        if exc_type is not None:
            self.log_event(
                event_type=EventType.ERROR,
                name=exc_type.__name__,
                error_type=exc_type.__name__,
                error_message=str(exc_val),
                metadata={"exception_class": exc_type.__qualname__},
            )
            self.finish(status=RunStatus.FAILED)
        else:
            self.finish(status=RunStatus.SUCCESS)
        await self._async_client.flush()
        return False
