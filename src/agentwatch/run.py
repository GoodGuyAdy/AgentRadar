"""AgentWatch AgentRun — context manager for tracking a single agent run."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator

from agentwatch.events import EventType, RunStatus, _new_id, _utcnow, build_event

if TYPE_CHECKING:
    from agentwatch.client import AgentWatch

logger = logging.getLogger("agentwatch")


class AgentRun:
    """Represents a single agent run.

    Use as a context manager for automatic start/finish tracking::

        with aw.start_run(agent_name="MyAgent") as run:
            run.log_event(event_type="tool_call", name="search")
    """

    def __init__(
        self,
        *,
        client: "AgentWatch",
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
        self._start(input=self._input, metadata=self._metadata)
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
            self._finish(status=RunStatus.FAILED)
        else:
            self._finish(status=RunStatus.SUCCESS)
        self._client.flush()
        return False  # do not suppress the exception

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_event(
        self,
        *,
        event_type: EventType | str,
        name: str | None = None,
        duration_ms: float | None = None,
        input: dict[str, Any] | None = None,
        output: dict[str, Any] | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        model_name: str | None = None,
        provider: str | None = None,
        token_usage: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Log an event on this run.  Returns the generated event_id."""
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
        input: dict[str, Any] | None = None,
        output: dict[str, Any] | None = None,
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
        input: dict[str, Any] | None = None,
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
        output: dict[str, Any] | None = None,
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _start(
        self,
        input: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._start_time = time.monotonic()
        self.log_event(
            event_type=EventType.RUN_STARTED,
            input=input,
            metadata=metadata,
        )

    def _finish(self, status: RunStatus) -> None:
        duration_ms: float | None = None
        if self._start_time is not None:
            duration_ms = (time.monotonic() - self._start_time) * 1000
        self.status = status
        self.log_event(
            event_type=EventType.RUN_FINISHED,
            duration_ms=duration_ms,
            metadata={"status": status.value},
        )
