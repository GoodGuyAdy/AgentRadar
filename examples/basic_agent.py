"""Basic agent example using the AgentRadar SDK."""
# Run: python examples/basic_agent.py

from agentradar import AgentRadar

# Initialize AgentRadar SDK
ar = AgentRadar(
    api_key="ar_live_your_key_here",
    endpoint="https://api.agent-radar.in",
    include_payloads=True,
)

with ar.start_run(
    agent_name="CustomerSupportAgent",
    input={"question": "Where is my order?"},
) as run:
    # 1. Simulate an LLM call
    run.log_llm_call(
        model_name="gpt-4o",
        provider="openai",
        input={"messages": [{"role": "user", "content": "Where is my order?"}]},
        output={"content": "Let me look up your order…"},
        duration_ms=850.0,
        token_usage={"prompt_tokens": 42, "completion_tokens": 15},
    )

    # 2. Simulate a tool call with context manager
    with run.track_tool("search_orders", input={"order_id": "ORD-123"}) as tool:
        tool.set_output({"status": "shipped", "eta": "2026-10-15"})

    # 3. Final LLM response
    run.log_llm_call(
        model_name="gpt-4o",
        provider="openai",
        input={"tool_output": {"status": "shipped"}},
        output={"content": "Your order was shipped and will arrive on Oct 15."},
        duration_ms=600.0,
        token_usage={"prompt_tokens": 60, "completion_tokens": 20},
    )

print(f"Run {run.run_id} completed with status: {run.status.value}")
