"""Basic agent example using the AgentWatch SDK."""
# Run: python examples/basic_agent.py

from agentwatch import AgentWatch

aw = AgentWatch(
    api_key="aw_live_your_key_here",
    endpoint="http://localhost:8000",
    include_payloads=True,
)

with aw.start_run(
    agent_name="CustomerSupportAgent",
    input={"question": "Where is my order?"},
) as run:
    # Simulate an LLM call
    run.log_llm_call(
        model_name="gpt-4o",
        provider="openai",
        input={"messages": [{"role": "user", "content": "Where is my order?"}]},
        output={"content": "Let me look up your order…"},
        duration_ms=850.0,
        token_usage={"prompt_tokens": 42, "completion_tokens": 15},
    )

    # Simulate a tool call
    run.log_tool_call(name="search_orders", input={"order_id": "ORD-123"})
    run.log_tool_result(
        name="search_orders",
        output={"status": "shipped", "eta": "2026-10-15"},
        duration_ms=120.0,
    )

    # Second LLM call with the tool result
    run.log_llm_call(
        model_name="gpt-4o",
        provider="openai",
        input={"tool_output": {"status": "shipped"}},
        output={"content": "Your order was shipped and will arrive on Oct 15."},
        duration_ms=600.0,
        token_usage={"prompt_tokens": 60, "completion_tokens": 20},
    )

print(f"Run {run.run_id} completed with status: {run.status.value}")
