# agentwatch — Python SDK

[![PyPI version](https://badge.fury.io/py/agentwatch.svg)](https://pypi.org/project/agentwatch/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**AI agent observability — track runs, LLM calls, tool calls, errors, and performance metrics in your AgentWatch dashboard.**

---

## Installation

```bash
pip install agentwatch
```

## Quick Start

```python
from agentwatch import AgentWatch

aw = AgentWatch(
    api_key="aw_live_your_key_here",
    endpoint="http://localhost:8000",  # your AgentWatch platform URL
)

with aw.start_run(
    agent_name="CustomerSupportAgent",
    input={"question": "Where is my order?"},
) as run:
    # Log an LLM call
    run.log_llm_call(
        model_name="gpt-4o",
        provider="openai",
        duration_ms=850.0,
        token_usage={"prompt_tokens": 42, "completion_tokens": 15},
    )

    # Log a tool call and its result
    run.log_tool_call(name="search_orders", input={"order_id": "123"})
    run.log_tool_result(
        name="search_orders",
        output={"status": "shipped"},
        duration_ms=120.0,
    )
```

## API Key Configuration

Get your API key from the AgentWatch dashboard under **Settings → API Keys**.

```python
# Option 1: Pass directly
aw = AgentWatch(api_key="aw_live_...")

# Option 2: Environment variable
# export AGENTWATCH_API_KEY=aw_live_...
aw = AgentWatch()
```

## Tracking a Run

```python
with aw.start_run(agent_name="MyAgent", input={"task": "..."}) as run:
    # Your agent code here
    run.log_event(
        event_type="tool_call",
        name="my_tool",
        input={"key": "value"},
    )
```

The run is automatically marked **success** on clean exit, or **failed** if an exception escapes the `with` block.

## Logging Events

### LLM Calls
```python
run.log_llm_call(
    model_name="claude-3-5-sonnet",
    provider="anthropic",
    duration_ms=1200.0,
    token_usage={"prompt_tokens": 100, "completion_tokens": 50},
)
```

### Tool Calls
```python
run.log_tool_call(name="web_search", input={"query": "latest AI news"})
run.log_tool_result(name="web_search", output={"results": [...]})
```

### Errors
```python
run.log_error(
    error_type="ToolTimeoutError",
    error_message="Tool timed out after 30s",
    name="web_search",
)
```

### Custom Events
```python
run.log_event(
    event_type="custom_event",
    name="my_event",
    metadata={"key": "value"},
)
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `api_key` | `$AGENTWATCH_API_KEY` | Your project API key |
| `endpoint` | `$AGENTWATCH_ENDPOINT` or `http://localhost:8000` | AgentWatch platform URL |
| `timeout` | `10.0` | HTTP request timeout in seconds |
| `max_retries` | `3` | Max retries for transient failures |
| `batch_size` | `50` | Events per batch (auto-flush trigger) |
| `enabled` | `True` | Set `False` to disable all telemetry |
| `include_payloads` | `False` | Send input/output content (may contain PII) |

## Batching and Flushing

Events are collected in memory and flushed:
- **Automatically** when the run context manager exits.
- **Automatically** when the buffer reaches `batch_size`.
- **Manually** via `aw.flush()`.

> **⚠ Delivery Guarantee**: The SDK makes a best-effort attempt to deliver events. It does **not** implement durable on-disk buffering. If the process crashes before `flush()` is called, buffered events will be lost.

## Privacy Options

By default, `input` and `output` payloads are **not sent** to protect sensitive data.

```python
# Enable payload capture (only if your data is safe to transmit)
aw = AgentWatch(api_key="...", include_payloads=True)
```

## Disabling Telemetry

```python
aw = AgentWatch(api_key="...", enabled=False)
```

All SDK calls become no-ops; no network requests are made.

## Error Handling

```python
from agentwatch.exceptions import AuthenticationError, APIError, NetworkError

try:
    aw.flush()
except AuthenticationError:
    print("Invalid API key")
except APIError as e:
    print(f"API error {e.status_code}: {e}")
except NetworkError:
    print("Could not reach AgentWatch backend")
```

## Troubleshooting

**`ConfigurationError: api_key is required`**
→ Pass `api_key=` or set `AGENTWATCH_API_KEY`.

**`AuthenticationError`**
→ Check that your API key is correct and hasn't been revoked.

**Events not appearing in dashboard**
→ Call `aw.flush()` explicitly or ensure the run context manager has exited.

## Local Development

```bash
git clone https://github.com/agentwatch/agentwatch-python
cd agentwatch-python
pip install -e ".[dev]"
pytest
```

## Publishing to PyPI

> **Note**: Check that the `agentwatch` package name is available on PyPI before publishing.

```bash
pip install build twine
python -m build
twine check dist/*
twine upload dist/*          # TestPyPI first: twine upload --repository testpypi dist/*
```

A GitHub Actions workflow at `.github/workflows/release.yml` handles CI and PyPI Trusted Publishing.

## License

MIT — see [LICENSE](LICENSE).
