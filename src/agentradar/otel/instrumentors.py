"""Auto-instrumentation — detect and enable framework instrumentors.

This module tries to import and activate the matching OpenInference or
OpenLLMetry instrumentor for each detected framework.  It never crashes the
host application:

* Missing instrumentor package → WARNING with the exact ``pip install`` command
* Instrumentor raises during ``instrument()`` → WARNING and skip
* Framework not installed → silently skipped

Supported frameworks and their instrumentor packages
------------------------------------------------------
| framework     | package (pip extra)                                         |
|---------------|-------------------------------------------------------------|
| openai        | openinference-instrumentation-openai                        |
| anthropic     | openinference-instrumentation-anthropic                     |
| langchain     | openinference-instrumentation-langchain                     |
| langgraph     | openinference-instrumentation-langchain (same)              |
| llama_index   | openinference-instrumentation-llama-index                   |
| crewai        | openinference-instrumentation-crewai                        |
| dspy          | openinference-instrumentation-dspy                          |
| haystack      | openinference-instrumentation-haystack                      |
| mistralai     | openinference-instrumentation-mistralai                     |
| cohere        | openinference-instrumentation-cohere                        |
| vertexai      | openinference-instrumentation-vertexai                      |
| bedrock       | openinference-instrumentation-bedrock                       |
| google_genai  | openinference-instrumentation-google-generativeai           |

OpenLLMetry instrumentors are also tried as a fallback.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from typing import Any

logger = logging.getLogger("agentradar.otel.instrumentors")

# ---------------------------------------------------------------------------
# Registry: (import_check, instrumentor_module, instrumentor_class, pip_extra)
# ---------------------------------------------------------------------------

_INSTRUMENTORS: list[tuple[str, str, str, str]] = [
    # (framework_module_to_detect, instrumentor_module, class_name, pip_package)
    (
        "openai",
        "openinference.instrumentation.openai",
        "OpenAIInstrumentor",
        "agentradar-sdk[openai]",
    ),
    (
        "anthropic",
        "openinference.instrumentation.anthropic",
        "AnthropicInstrumentor",
        "agentradar-sdk[anthropic]",
    ),
    (
        "langchain",
        "openinference.instrumentation.langchain",
        "LangChainInstrumentor",
        "agentradar-sdk[langchain]",
    ),
    (
        "langgraph",
        "openinference.instrumentation.langchain",
        "LangChainInstrumentor",
        "agentradar-sdk[langchain]",
    ),
    (
        "llama_index",
        "openinference.instrumentation.llama_index",
        "LlamaIndexInstrumentor",
        "agentradar-sdk[llamaindex]",
    ),
    (
        "crewai",
        "openinference.instrumentation.crewai",
        "CrewAIInstrumentor",
        "agentradar-sdk[crewai]",
    ),
    (
        "dspy",
        "openinference.instrumentation.dspy",
        "DSPyInstrumentor",
        "agentradar-sdk[dspy]",
    ),
    (
        "haystack",
        "openinference.instrumentation.haystack",
        "HaystackInstrumentor",
        "agentradar-sdk[haystack]",
    ),
    (
        "mistralai",
        "openinference.instrumentation.mistralai",
        "MistralAIInstrumentor",
        "agentradar-sdk[mistralai]",
    ),
    (
        "cohere",
        "openinference.instrumentation.cohere",
        "CohereInstrumentor",
        "agentradar-sdk[cohere]",
    ),
    (
        "vertexai",
        "openinference.instrumentation.vertexai",
        "VertexAIInstrumentor",
        "agentradar-sdk[vertexai]",
    ),
    (
        "boto3",  # AWS Bedrock uses boto3
        "openinference.instrumentation.bedrock",
        "BedrockInstrumentor",
        "agentradar-sdk[bedrock]",
    ),
    (
        "google.generativeai",
        "openinference.instrumentation.google_generativeai",
        "GoogleGenerativeAIInstrumentor",
        "agentradar-sdk[google-genai]",
    ),
]

# Map short framework names (as used in frameworks=[...]) to their entry
_NAME_TO_ENTRY: dict[str, tuple[str, str, str, str]] = {
    "openai": _INSTRUMENTORS[0],
    "anthropic": _INSTRUMENTORS[1],
    "langchain": _INSTRUMENTORS[2],
    "langgraph": _INSTRUMENTORS[3],
    "llama_index": _INSTRUMENTORS[4],
    "llamaindex": _INSTRUMENTORS[4],
    "crewai": _INSTRUMENTORS[5],
    "dspy": _INSTRUMENTORS[6],
    "haystack": _INSTRUMENTORS[7],
    "mistralai": _INSTRUMENTORS[8],
    "cohere": _INSTRUMENTORS[9],
    "vertexai": _INSTRUMENTORS[10],
    "bedrock": _INSTRUMENTORS[11],
    "google_genai": _INSTRUMENTORS[12],
    "google-genai": _INSTRUMENTORS[12],
}


def _is_installed(module_name: str) -> bool:
    """Return True if a top-level module is importable."""
    return importlib.util.find_spec(module_name) is not None


def _activate_instrumentor(entry: tuple[str, str, str, str], tracer_provider: Any) -> bool:
    """Try to import and call .instrument() on one instrumentor.

    Returns True on success, False on any failure.
    """
    framework_mod, instr_mod, instr_cls, pip_extra = entry
    try:
        mod = importlib.import_module(instr_mod)
        cls = getattr(mod, instr_cls)
        instance = cls()
        instance.instrument(tracer_provider=tracer_provider)
        logger.debug("Enabled instrumentor: %s (%s)", instr_cls, instr_mod)
        return True
    except ImportError:
        logger.warning(
            "AgentRadar: instrumentor for '%s' not installed. "
            "Run:  pip install '%s'",
            framework_mod,
            pip_extra,
        )
        return False
    except Exception as exc:
        logger.warning(
            "AgentRadar: failed to activate instrumentor %s: %s",
            instr_cls,
            exc,
        )
        return False


def auto_instrument(tracer_provider: Any) -> list[str]:
    """Detect installed frameworks and activate matching instrumentors.

    Returns a list of successfully activated framework names.
    """
    activated: list[str] = []
    seen_modules: set[str] = set()  # avoid double-activating (e.g. langchain + langgraph)

    for entry in _INSTRUMENTORS:
        framework_mod, instr_mod, instr_cls, _ = entry
        if not _is_installed(framework_mod):
            continue
        if instr_mod in seen_modules:
            continue
        if _activate_instrumentor(entry, tracer_provider):
            activated.append(framework_mod)
            seen_modules.add(instr_mod)

    if activated:
        logger.info("AgentRadar auto-instrumentation enabled for: %s", ", ".join(activated))
    else:
        logger.debug("AgentRadar: no supported frameworks detected for auto-instrumentation.")
    return activated


def instrument_frameworks(frameworks: list[str], tracer_provider: Any) -> list[str]:
    """Activate instrumentors for an explicit list of framework names.

    Warns (does not raise) for unknown or un-instrumentable names.
    Returns a list of successfully activated framework names.
    """
    activated: list[str] = []
    seen_modules: set[str] = set()

    for name in frameworks:
        key = name.lower().replace("-", "_")
        entry = _NAME_TO_ENTRY.get(key)
        if entry is None:
            logger.warning(
                "AgentRadar: unknown framework '%s'. "
                "Supported: %s",
                name,
                ", ".join(sorted(_NAME_TO_ENTRY.keys())),
            )
            continue
        _, instr_mod, instr_cls, _ = entry
        if instr_mod in seen_modules:
            continue
        if _activate_instrumentor(entry, tracer_provider):
            activated.append(name)
            seen_modules.add(instr_mod)

    return activated
