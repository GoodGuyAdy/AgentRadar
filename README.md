# agentradar-sdk — Python SDK

[![PyPI version](https://badge.fury.io/py/agentradar-sdk.svg)](https://pypi.org/project/agentradar-sdk/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Next-generation AI agent observability — zero-code OpenTelemetry tracing for OpenAI, Anthropic, LangChain, CrewAI, LlamaIndex, and custom agents.**

---

## ⚡ Zero-Code Quick Start

Trace your entire agent execution, tool calls, and LLM completions with **two lines of code**. No wrappers, no manual run creation, zero disruption to your existing code.

### 1. Install

Install with your framework extra:

```bash
# For OpenAI
pip install "agentradar-sdk[openai]"

# For Anthropic
pip install "agentradar-sdk[anthropic]"

# For LangChain / LangGraph
pip install "agentradar-sdk[langchain]"

# For all supported frameworks
pip install "agentradar-sdk[all]"
```

### 2. Initialize in 2 Lines

Add `agentradar.init()` before running your agent code:

```python
import agentradar
agentradar.init(api_key="ar_live_your_key_here")  # or set AGENTRADAR_API_KEY env var

# Your existing agent code runs unchanged!
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Analyze our quarterly churn rate."}],
)
```

All runs, token counts, latencies, model parameters, and errors are automatically streamed to your [AgentRadar dashboard](https://agent-radar.in).

---

## 🧩 Supported Frameworks

`agentradar.init()` uses OpenTelemetry and open-source OpenInference / OpenLLMetry instrumentors under the hood. It automatically detects installed packages and instruments them:

| Framework | Installation Extra | Auto-Detected Package |
|---|---|---|
| **OpenAI** | `pip install "agentradar-sdk[openai]"` | `openai` |
| **Anthropic** | `pip install "agentradar-sdk[anthropic]"` | `anthropic` |
| **LangChain** | `pip install "agentradar-sdk[langchain]"` | `langchain`, `langchain-core` |
| **LangGraph** | `pip install "agentradar-sdk[langchain]"` | `langgraph` |
| **LlamaIndex** | `pip install "agentradar-sdk[llamaindex]"` | `llama_index` |
| **CrewAI** | `pip install "agentradar-sdk[crewai]"` | `crewai` |
| **DSPy** | `pip install "agentradar-sdk[dspy]"` | `dspy` |
| **Haystack** | `pip install "agentradar-sdk[haystack]"` | `haystack` |
| **Mistral** | `pip install "agentradar-sdk[mistralai]"` | `mistralai` |
| **Cohere** | `pip install "agentradar-sdk[cohere]"` | `cohere` |
| **AWS Bedrock** | `pip install "agentradar-sdk[bedrock]"` | `boto3` |
| **Google GenAI** | `pip install "agentradar-sdk[google-genai]"` | `google.generativeai` |

You can also specify which frameworks to activate:
```python
agentradar.init(frameworks=["openai", "langchain"])
```

---

## 🔒 Privacy-First Design

By default, AgentRadar protects sensitive customer data with defense-in-depth:

* **Payload Stripping Enabled by Default (`include_payloads=False`)**: Prompt messages, completion text, and tool input/output contents are stripped on the client side before export. Latency, token metrics, error types, model names, and execution hierarchies are preserved.
* To retain inputs and outputs for prompt debugging:
  ```python
  agentradar.init(include_payloads=True)
  ```

---

## 🛠️ Tracing Plain-Python Agents (`@agent` & `@tool`)

For custom functions or multi-step Python agents, use lightweight decorators:

```python
import agentradar
from agentradar import agent, tool

agentradar.init(api_key="ar_live_...")

@tool("calculator")
def multiply(a: float, b: float) -> float:
    return a * b

@agent("MathAssistant")
def run_assistant(x: float, y: float):
    return multiply(x, y)

run_assistant(10, 5)
```
Works seamlessly with synchronous functions and async coroutines (`async def`).

---

## 🌐 OTel-Without-SDK (Direct OTLP Ingestion)

Already using OpenTelemetry collector, OpenLLMetry, or custom OTLP exporters? You can stream directly into AgentRadar without our SDK:

* **Endpoint**: `https://api.agent-radar.in/api/v1/traces`
* **Protocols**: OTLP/HTTP with `Content-Type: application/x-protobuf` or `application/json`
* **Authentication**: Include `Authorization: Bearer ar_live_...` or `X-API-Key: ar_live_...`

Example with standard OpenTelemetry exporter:
```bash
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="https://api.agent-radar.in/api/v1/traces"
export OTEL_EXPORTER_OTLP_TRACES_HEADERS="Authorization=Bearer ar_live_your_key_here"
```

---

## ⚙️ Configuration & Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `AGENTRADAR_API_KEY` (or `AR_API_KEY`) | API key from dashboard | Required |
| `AGENTRADAR_ENDPOINT` | Ingestion base URL | `https://api.agent-radar.in` |
| `OTEL_SERVICE_NAME` | Service name resource attribute | `agentradar-app` |
| `AGENTRADAR_ENABLED` | Set to `0` or `false` to disable tracing | `true` |

---

## 📚 Advanced / Manual Tracing

The SDK preserves 100% backward compatibility with the manual programmatic API:

```python
from agentradar import AgentRadar

ar = AgentRadar(api_key="ar_live_...")

with ar.start_run(agent_name="CustomAgent", input={"query": "test"}) as run:
    run.log_llm_call(
        model_name="gpt-4o",
        provider="openai",
        duration_ms=650.0,
        token_usage={"prompt_tokens": 50, "completion_tokens": 20},
    )

    with run.track_tool("db_search", input={"id": 123}) as tool:
        tool.set_output({"status": "found"})
```

Async manual tracing is also fully supported with `AsyncAgentRadar`:

```python
from agentradar import AsyncAgentRadar

async with AsyncAgentRadar(api_key="ar_live_...") as ar:
    async with ar.start_run("AsyncAgent") as run:
        run.log_llm_call(model_name="claude-3-5-sonnet", provider="anthropic", duration_ms=450.0)
```

---

## 📄 License

MIT © [AgentRadar](https://agent-radar.in)
