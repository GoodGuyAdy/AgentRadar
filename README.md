# agentradar-sdk — Python SDK

[![PyPI version](https://badge.fury.io/py/agentradar-sdk.svg)](https://pypi.org/project/agentradar-sdk/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**AI agent observability SDK — track runs, LLM executions, tool calls, errors, latency, and performance metrics in your AgentRadar dashboard.**

---

## Installation

```bash
pip install agentradar-sdk
```

## Quick Start

```python
from agentradar import AgentRadar

ar = AgentRadar(
    api_key="ar_live_your_key_here",
    # endpoint defaults to "https://api.agent-radar.in"
)

with ar.start_run(
    agent_name="CustomerSupportAgent",
    input={"question": "Where is my order?"},
) as run:
    # 1. Log an LLM call
    run.log_llm_call(
        model_name="gpt-4o",
        provider="openai",
        duration_ms=850.0,
        token_usage={"prompt_tokens": 42, "completion_tokens": 15},
    )

    # 2. Track a tool call (with automatic duration measurement)
    with run.track_tool("search_orders", input={"order_id": "123"}) as tool:
        tool.set_output({"status": "shipped", "carrier": "FedEx"})
```

The run is automatically marked **success** on clean exit, or **failed** if an exception escapes the `with` block.

---

## API Key Configuration

Get your API key from the AgentRadar dashboard at [https://agent-radar.in](https://agent-radar.in) under **Settings → API Keys**. Keys are prefixed with `ar_live_`.

For interactive OpenAPI/Swagger reference, visit [https://api.agent-radar.in/docs](https://api.agent-radar.in/docs).

```python
# Option 1: Pass directly
ar = AgentRadar(api_key="ar_live_...")

# Option 2: Environment variable (AGENTRADAR_API_KEY or AR_API_KEY)
# export AGENTRADAR_API_KEY=ar_live_...
ar = AgentRadar()
```

---

## Asynchronous Agents (`AsyncAgentRadar`)

For async agent frameworks (LangChain, AutoGen, CrewAI, FastAPI):

```python
import asyncio
from agentradar import AsyncAgentRadar

async def main():
    async with AsyncAgentRadar(api_key="ar_live_...") as ar:
        async with ar.start_run("ResearchAgent", input={"topic": "Agent observability"}) as run:
            run.log_llm_call(model_name="claude-3-5-sonnet", provider="anthropic", duration_ms=450.0)
            with run.track_tool("web_search", input={"q": "Observability"}) as tool:
                tool.set_output({"count": 10})

asyncio.run(main())
```

---

## Tracking Tool Calls & LLM Calls

### Convenience Context Managers

#### Tool Calls (`run.track_tool`)
Automatically starts timer, logs `tool_call`, catches exceptions (logging `error`), and logs `tool_result` with duration:

```python
with run.track_tool("database_query", input={"user_id": 42}) as tool:
    result = db.query(user_id=42)
    tool.set_output(result)
```

#### LLM Reasoning (`run.track_llm`)
```python
with run.track_llm(model_name="gpt-4o", provider="openai", input={"prompt": "Summarize"}) as llm:
    completion = openai_client.chat.completions.create(...)
    llm.set_result(
        output={"text": completion.choices[0].message.content},
        token_usage={"prompt_tokens": 100, "completion_tokens": 50},
    )
```

### Manual Logging Helpers

#### LLM Call
```python
run.log_llm_call(
    model_name="claude-3-5-sonnet",
    provider="anthropic",
    input={"prompt": "..."},
    output={"response": "..."},
    duration_ms=1200.0,
    token_usage={"prompt_tokens": 100, "completion_tokens": 50},
)
```

#### Tool Call & Result
```python
run.log_tool_call(name="web_search", input={"query": "latest AI news"})
run.log_tool_result(name="web_search", output={"results": [...]}, duration_ms=350.0)
```

#### Error Logging
```python
run.log_error(
    error_type="ToolTimeoutError",
    error_message="Tool timed out after 30s",
    name="web_search",
)
```

#### Custom Events
```python
run.log_custom_event(
    name="workflow_checkpoint",
    metadata={"step": 2, "state": "validating"},
)
```

---

## Manual Run Lifecycle (Without Context Manager)

If you need manual control over run boundaries:

```python
run = ar.start_run(agent_name="PipelineAgent", input={"batch_id": 99})
run.start()

# Do agent work...
run.log_tool_call(name="process_item")

run.finish(status="success")  # or status="failed"
ar.flush()
```

---

## Single Event Ingestion & Health Check

```python
# Check backend health
status = ar.check_health()
print(f"Backend status: {status.status}, version: {status.version}")

# Direct single-event ingestion
ar.send_event({
    "event_id": "...",
    "run_id": "...",
    "agent_name": "...",
    "event_type": "custom",
    "timestamp": "2026-10-16T12:00:00Z"
})
```

---

## Configuration Options

| Parameter | Default | Environment Variable | Description |
|-----------|---------|----------------------|-------------|
| `api_key` | `""` | `AGENTRADAR_API_KEY`, `AR_API_KEY` | Your project API key (`ar_live_...`) |
| `endpoint` | `https://api.agent-radar.in` | `AGENTRADAR_ENDPOINT`, `AR_ENDPOINT` | AgentRadar platform backend URL |
| `auth_token` | `None` | `AGENTRADAR_AUTH_TOKEN`, `AR_AUTH_TOKEN` | Optional Bearer JWT for platform API access |
| `timeout` | `10.0` | — | HTTP request timeout in seconds |
| `max_retries` | `3` | — | Max retries for transient 5xx/network errors |
| `batch_size` | `50` | — | Events per batch (auto-flush trigger) |
| `enabled` | `True` | — | Set `False` to disable all telemetry |
| `include_payloads` | `False` | — | Send input/output content (may contain PII) |

---

## Privacy & Payload Gating

By default, `input` and `output` payloads are **not sent** to protect sensitive user data and credentials.

```python
# Enable payload capture (only if your data is safe to transmit)
ar = AgentRadar(api_key="ar_live_...", include_payloads=True)
```

---

## Error Handling & Resilience

The SDK automatically retries on transient network errors and server errors (`500`, `502`, `503`, `504`) with exponential backoff:

```python
from agentradar.exceptions import AuthenticationError, APIError, NetworkError

try:
    ar.flush()
except AuthenticationError:
    print("Invalid or revoked API key")
except APIError as e:
    print(f"API error ({e.status_code}): {e}")
except NetworkError:
    print("Could not reach AgentRadar backend after retries")
```

---

## Local Development & Testing

```bash
git clone https://github.com/GoodGuyAdy/AgentRadar
cd AgentRadar
pip install -e ".[dev]"
pytest
```

---

## License

MIT — see [LICENSE](LICENSE).
