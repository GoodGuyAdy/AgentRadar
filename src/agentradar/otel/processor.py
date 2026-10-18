"""Privacy-gating SpanProcessor.

When ``include_payloads=False`` (the default), this processor strips prompt /
completion / input / output content from spans BEFORE they are exported.
This is SDK-side defense-in-depth; the backend also strips server-side when
``project.include_payloads`` is False.

The processor runs synchronously in the exporter's batch thread so it never
blocks the host application.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from opentelemetry.sdk.trace import ReadableSpan, Span
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace import SpanProcessor

if TYPE_CHECKING:
    pass

# Attribute keys whose values are considered payload content.
# Any key in this set is removed from spans before export when
# include_payloads=False.
_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        # OpenInference
        "input.value",
        "output.value",
        "llm.input_messages",
        "llm.output_messages",
        "llm.prompts",
        "llm.prompt_template.template",
        # GenAI semconv
        "gen_ai.prompt",
        "gen_ai.completion",
        "gen_ai.request.messages",
        "gen_ai.response.message",
        # OpenLLMetry
        "llm.request.data",
        "llm.response.data",
        "traceloop.entity.input",
        "traceloop.entity.output",
        # Generic
        "db.statement",           # may contain sensitive query data
    }
)

# Event names whose entire attribute set may contain payload content.
_PAYLOAD_EVENT_NAMES: frozenset[str] = frozenset(
    {
        "gen_ai.content.prompt",
        "gen_ai.content.completion",
        "llm.content.prompt",
        "llm.content.completion",
    }
)


class PayloadStrippingProcessor(SpanProcessor):
    """A SpanProcessor that strips payload attributes before export.

    This is a *read-write* processor: it wraps the underlying exporter and
    filters spans immediately before they are handed to the exporter's
    ``export()`` call.  It does NOT modify the live span object so it never
    interferes with the host application's tracing.

    Usage::

        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from agentradar.otel.processor import PayloadStrippingProcessor

        exporter = OTLPSpanExporter(...)
        batch = BatchSpanProcessor(exporter)
        stripping_batch = PayloadStrippingProcessor(batch)
        provider.add_span_processor(stripping_batch)
    """

    def __init__(self, wrapped: SpanProcessor) -> None:
        self._wrapped = wrapped

    # ------------------------------------------------------------------
    # SpanProcessor protocol (delegate everything except on_end)
    # ------------------------------------------------------------------

    def on_start(self, span: Span, parent_context: object = None) -> None:  # type: ignore[override]
        self._wrapped.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        stripped = _strip_span(span)
        self._wrapped.on_end(stripped)

    def shutdown(self) -> None:
        self._wrapped.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self._wrapped.force_flush(timeout_millis)


# ---------------------------------------------------------------------------
# Internal stripping logic
# ---------------------------------------------------------------------------


def _strip_span(span: ReadableSpan) -> ReadableSpan:
    """Return a copy of ``span`` with all payload attributes/events removed.

    We monkey-patch the private ``_attributes`` and ``_events`` fields on a
    shallow copy so we never mutate the live span that the application might
    still hold a reference to.
    """
    import copy

    stripped = copy.copy(span)  # shallow copy — same underlying immutable fields

    # Strip attributes
    orig_attrs = span.attributes or {}
    new_attrs = {k: v for k, v in orig_attrs.items() if k not in _PAYLOAD_KEYS}
    object.__setattr__(stripped, "_attributes", new_attrs)

    # Strip payload events (by name) or their content attributes
    orig_events = span.events or ()
    new_events = []
    for ev in orig_events:
        if ev.name in _PAYLOAD_EVENT_NAMES:
            continue  # drop entire event
        # Also strip payload keys from per-event attributes
        ev_attrs = ev.attributes or {}
        if any(k in _PAYLOAD_KEYS for k in ev_attrs):
            from opentelemetry.sdk.trace import Event as _Event  # type: ignore[attr-defined]
            clean_ev_attrs = {k: v for k, v in ev_attrs.items() if k not in _PAYLOAD_KEYS}
            try:
                ev = _Event(
                    name=ev.name,
                    attributes=clean_ev_attrs,
                    timestamp=ev.timestamp,
                )
            except Exception:
                pass  # if Event constructor changes, keep original
        new_events.append(ev)

    object.__setattr__(stripped, "_events", tuple(new_events))
    return stripped
