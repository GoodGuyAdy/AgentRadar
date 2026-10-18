"""OTel-based decorators for plain-Python custom agents and tools.

Provides:
- `@agent("AgentName")` or `@agent` — traces an agent execution
- `@tool("ToolName")` or `@tool` — traces a tool execution

Both decorators create OpenTelemetry spans with OpenInference semantic
conventions (e.g. `openinference.span.kind = "AGENT"` or `"TOOL"`),
meaning they are automatically recognized by AgentRadar's trace mapper and
displayed seamlessly in the dashboard.
"""

from __future__ import annotations

import functools
import inspect
import json
from typing import Any, Callable, TypeVar, cast, overload

from opentelemetry import trace as otel_trace
from opentelemetry.trace import StatusCode

F = TypeVar("F", bound=Callable[..., Any])


def _safe_serialize(val: Any) -> str:
    """Best-effort JSON serialization; falls back to str()."""
    try:
        return json.dumps(val, default=str)
    except Exception:
        return str(val)


def agent(
    name_or_func: str | Callable[..., Any] | None = None,
    *,
    name: str | None = None,
) -> Any:
    """Decorator to trace an agent function or method.

    Usage:
        @agent
        def my_agent(prompt: str) -> str:
            ...

        @agent("ResearchAssistant")
        async def run_assistant(query: str):
            ...
    """

    def decorator(fn: F) -> F:
        agent_name = name or (name_or_func if isinstance(name_or_func, str) else None) or fn.__name__

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                tracer = otel_trace.get_tracer("agentradar")
                with tracer.start_as_current_span(agent_name) as span:
                    span.set_attribute("openinference.span.kind", "AGENT")
                    span.set_attribute("agent.name", agent_name)
                    span.set_attribute("gen_ai.agent.name", agent_name)
                    if args or kwargs:
                        call_input = {"args": args, "kwargs": kwargs} if kwargs else list(args)
                        span.set_attribute("input.value", _safe_serialize(call_input))
                    try:
                        result = await fn(*args, **kwargs)
                        if result is not None:
                            span.set_attribute("output.value", _safe_serialize(result))
                        span.set_status(StatusCode.OK)
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(StatusCode.ERROR, str(exc))
                        raise

            return cast(F, async_wrapper)

        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                tracer = otel_trace.get_tracer("agentradar")
                with tracer.start_as_current_span(agent_name) as span:
                    span.set_attribute("openinference.span.kind", "AGENT")
                    span.set_attribute("agent.name", agent_name)
                    span.set_attribute("gen_ai.agent.name", agent_name)
                    if args or kwargs:
                        call_input = {"args": args, "kwargs": kwargs} if kwargs else list(args)
                        span.set_attribute("input.value", _safe_serialize(call_input))
                    try:
                        result = fn(*args, **kwargs)
                        if result is not None:
                            span.set_attribute("output.value", _safe_serialize(result))
                        span.set_status(StatusCode.OK)
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(StatusCode.ERROR, str(exc))
                        raise

            return cast(F, sync_wrapper)

    if callable(name_or_func):
        return decorator(name_or_func)
    return decorator


def tool(
    name_or_func: str | Callable[..., Any] | None = None,
    *,
    name: str | None = None,
) -> Any:
    """Decorator to trace a tool function or method.

    Usage:
        @tool
        def calculate(expression: str) -> float:
            ...

        @tool("web_search")
        async def search(query: str):
            ...
    """

    def decorator(fn: F) -> F:
        tool_name = name or (name_or_func if isinstance(name_or_func, str) else None) or fn.__name__

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                tracer = otel_trace.get_tracer("agentradar")
                with tracer.start_as_current_span(tool_name) as span:
                    span.set_attribute("openinference.span.kind", "TOOL")
                    span.set_attribute("tool.name", tool_name)
                    span.set_attribute("gen_ai.tool.name", tool_name)
                    if args or kwargs:
                        call_input = {"args": args, "kwargs": kwargs} if kwargs else list(args)
                        span.set_attribute("input.value", _safe_serialize(call_input))
                    try:
                        result = await fn(*args, **kwargs)
                        if result is not None:
                            span.set_attribute("output.value", _safe_serialize(result))
                        span.set_status(StatusCode.OK)
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(StatusCode.ERROR, str(exc))
                        raise

            return cast(F, async_wrapper)

        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                tracer = otel_trace.get_tracer("agentradar")
                with tracer.start_as_current_span(tool_name) as span:
                    span.set_attribute("openinference.span.kind", "TOOL")
                    span.set_attribute("tool.name", tool_name)
                    span.set_attribute("gen_ai.tool.name", tool_name)
                    if args or kwargs:
                        call_input = {"args": args, "kwargs": kwargs} if kwargs else list(args)
                        span.set_attribute("input.value", _safe_serialize(call_input))
                    try:
                        result = fn(*args, **kwargs)
                        if result is not None:
                            span.set_attribute("output.value", _safe_serialize(result))
                        span.set_status(StatusCode.OK)
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(StatusCode.ERROR, str(exc))
                        raise

            return cast(F, sync_wrapper)

    if callable(name_or_func):
        return decorator(name_or_func)
    return decorator
