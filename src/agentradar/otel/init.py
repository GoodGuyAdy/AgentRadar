"""agentradar.init() — zero-code OTel instrumentation setup.

This module wires up a BatchSpanProcessor + OTLP/HTTP exporter pointing at
the AgentRadar backend, optionally wrapping it in a PayloadStrippingProcessor.
It also activates framework instrumentors (auto-detected or explicit).

Design constraints
------------------
* NEVER breaks or blocks the host app — all setup in try/except.
* Idempotent — calling init() twice is a no-op after the first call.
* Backward-compatible — does not touch AgentRadar / AgentRun / manual API.
* Minimal core footprint — only opentelemetry-api/sdk/exporter-otlp-proto-http
  are hard dependencies; framework instrumentors are optional extras.
* atexit flush — short scripts don't lose their last batch.
"""

from __future__ import annotations

import atexit
import logging
import os
import threading
from typing import Any

logger = logging.getLogger("agentradar")

# ---------------------------------------------------------------------------
# Module-level state (guards idempotency)
# ---------------------------------------------------------------------------

_init_lock = threading.Lock()
_initialized = False
_provider: Any = None        # the TracerProvider we configured
_span_processor: Any = None  # the BatchSpanProcessor (or wrapping processor)


def _reset_for_testing() -> None:
    """Internal — reset global state so unit tests can call init() multiple times."""
    global _initialized, _provider, _span_processor
    with _init_lock:
        _initialized = False
        _provider = None
        _span_processor = None
        from opentelemetry import trace as otel_trace
        from opentelemetry.util._once import Once
        otel_trace._TRACER_PROVIDER_SET_ONCE = Once()
        otel_trace._TRACER_PROVIDER = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init(
    api_key: str | None = None,
    *,
    endpoint: str | None = None,
    frameworks: str | list[str] = "auto",
    include_payloads: bool = False,
    agent_name: str | None = None,
    service_name: str | None = None,
    metadata: dict[str, Any] | None = None,
    enabled: bool = True,
    **opts: Any,
) -> None:
    """Initialise AgentRadar OTel auto-instrumentation.

    Parameters
    ----------
    api_key:
        Your AgentRadar API key (``ar_live_…``).  Falls back to
        ``AGENTRADAR_API_KEY``, ``AR_API_KEY``, ``AGENT_RADAR_API_KEY``.
    endpoint:
        Backend base URL.  Defaults to ``https://api.agent-radar.in``.
        Falls back to ``AGENTRADAR_ENDPOINT`` / ``AR_ENDPOINT``.
    frameworks:
        ``"auto"`` (default) — detect installed frameworks and instrument them.
        ``["openai", "langchain"]`` — explicit list of frameworks to instrument.
        ``[]`` or ``None`` — skip auto-instrumentation (OTel still set up).
    include_payloads:
        When ``False`` (default) prompt / completion / input / output content
        attributes are stripped from spans before export.
    agent_name:
        Sets the default agent name for this service/run.  Alias for ``service_name``.
        Falls back to ``AGENTRADAR_AGENT_NAME``, ``OTEL_SERVICE_NAME``, or ``"agentradar-app"``.
    service_name:
        Sets the OTel ``service.name`` resource attribute.
    enabled:
        ``False`` → full no-op.  Useful for local dev / tests.
    **opts:
        Reserved for future keyword arguments (ignored for now).
    """
    global _initialized, _provider, _span_processor

    if not enabled:
        logger.debug("AgentRadar: OTel init skipped (enabled=False).")
        return

    with _init_lock:
        if _initialized:
            logger.debug("AgentRadar: init() called again — skipping (already initialised).")
            return

        try:
            _do_init(
                api_key=api_key,
                endpoint=endpoint,
                frameworks=frameworks,
                include_payloads=include_payloads,
                agent_name=agent_name,
                service_name=service_name,
                metadata=metadata,
                **opts,
            )
            _initialized = True
        except Exception as exc:
            logger.warning(
                "AgentRadar: OTel setup failed (%s). "
                "Your application will continue normally without AgentRadar tracing.",
                exc,
            )


def shutdown() -> None:
    """Flush and shut down the OTel TracerProvider.

    Registered automatically via ``atexit``; also callable explicitly.
    """
    global _provider, _span_processor
    if _provider is None:
        return
    try:
        _provider.shutdown()
        logger.debug("AgentRadar: TracerProvider shut down.")
    except Exception as exc:
        logger.debug("AgentRadar: error during shutdown: %s", exc)


def flush(timeout_ms: int = 5_000) -> None:
    """Force-flush the span batch processor.

    Useful in short-lived scripts to ensure all spans are exported before exit.
    """
    if _span_processor is None:
        return
    try:
        _span_processor.force_flush(timeout_ms)
    except Exception as exc:
        logger.debug("AgentRadar: flush error: %s", exc)


# ---------------------------------------------------------------------------
# Internal setup
# ---------------------------------------------------------------------------


def _do_init(
    *,
    api_key: str | None,
    endpoint: str | None,
    frameworks: str | list[str],
    include_payloads: bool,
    agent_name: str | None = None,
    service_name: str | None = None,
    metadata: dict[str, Any] | None = None,
    **opts: Any,
) -> None:
    """Actual setup — called once, inside the lock, exceptions bubble up."""
    global _provider, _span_processor

    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    from agentradar.otel.processor import PayloadStrippingProcessor

    # ------------------------------------------------------------------
    # Resolve config from args / env vars
    # ------------------------------------------------------------------
    resolved_key = (
        api_key
        or os.environ.get("AGENTRADAR_API_KEY")
        or os.environ.get("AR_API_KEY")
        or os.environ.get("AGENT_RADAR_API_KEY")
        or ""
    )
    if not resolved_key:
        raise ValueError(
            "AgentRadar api_key is required. Pass it explicitly or set AGENTRADAR_API_KEY."
        )

    resolved_endpoint = (
        endpoint
        or os.environ.get("AGENTRADAR_ENDPOINT")
        or os.environ.get("AR_ENDPOINT")
        or os.environ.get("AGENT_RADAR_ENDPOINT")
        or "https://api.agent-radar.in"
    ).rstrip("/")

    resolved_service = (
        agent_name
        or service_name
        or opts.get("agent_name")
        or os.environ.get("AGENTRADAR_AGENT_NAME")
        or os.environ.get("AR_AGENT_NAME")
        or os.environ.get("OTEL_SERVICE_NAME")
        or "agentradar-app"
    )

    traces_endpoint = f"{resolved_endpoint}/api/v1/traces"

    # ------------------------------------------------------------------
    # OTLP exporter
    # ------------------------------------------------------------------
    exporter = OTLPSpanExporter(
        endpoint=traces_endpoint,
        headers={"Authorization": f"Bearer {resolved_key}"},
    )

    # ------------------------------------------------------------------
    # Batch processor (optionally wrapped with payload stripping)
    # ------------------------------------------------------------------
    batch = BatchSpanProcessor(exporter)

    if include_payloads:
        active_processor = batch
    else:
        active_processor = PayloadStrippingProcessor(batch)

    _span_processor = active_processor

    # ------------------------------------------------------------------
    # TracerProvider — reuse existing global if already configured
    # ------------------------------------------------------------------
    existing_provider = otel_trace.get_tracer_provider()

    # Check if the existing provider is a real TracerProvider (not the no-op proxy)
    if isinstance(existing_provider, TracerProvider):
        # User already has a provider — just add our processor to it
        existing_provider.add_span_processor(active_processor)
        _provider = existing_provider
        logger.debug(
            "AgentRadar: added processor to existing TracerProvider (endpoint=%s)",
            traces_endpoint,
        )
    else:
        # No provider yet — create one and set it as the global
        import json
        resource_attrs: dict[str, Any] = {SERVICE_NAME: resolved_service}
        if metadata:
            for k, v in metadata.items():
                if isinstance(v, (str, bool, int, float)):
                    resource_attrs[f"metadata.{k}"] = v
                else:
                    resource_attrs[f"metadata.{k}"] = json.dumps(v)
            resource_attrs["metadata"] = json.dumps(metadata)
        resource = Resource.create(resource_attrs)
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(active_processor)
        otel_trace.set_tracer_provider(provider)
        _provider = provider
        logger.debug(
            "AgentRadar: created new TracerProvider (service=%s, endpoint=%s)",
            resolved_service,
            traces_endpoint,
        )

    # ------------------------------------------------------------------
    # Auto-instrumentation
    # ------------------------------------------------------------------
    _activate_frameworks(frameworks, _provider)

    # ------------------------------------------------------------------
    # atexit flush so short scripts don't lose the last batch
    # ------------------------------------------------------------------
    atexit.register(shutdown)

    logger.info(
        "AgentRadar OTel tracing initialised → %s (payloads=%s)",
        traces_endpoint,
        include_payloads,
    )


def _activate_frameworks(frameworks: str | list[str] | None, provider: Any) -> None:
    """Activate framework instrumentors based on the ``frameworks`` argument."""
    if not frameworks:
        return

    try:
        from agentradar.otel.instrumentors import auto_instrument, instrument_frameworks
    except ImportError as exc:
        logger.warning("AgentRadar: could not import instrumentors module: %s", exc)
        return

    try:
        if frameworks == "auto":
            auto_instrument(provider)
        elif isinstance(frameworks, (list, tuple)):
            instrument_frameworks(list(frameworks), provider)
    except Exception as exc:
        logger.warning("AgentRadar: auto-instrumentation setup failed: %s", exc)
