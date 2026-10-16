"""Simulated agent example — runs without any external AI API keys.

This example demonstrates how the SDK works end-to-end using simulated data.
Run: python examples/simulated_agent.py
"""

import time

from agentradar import AgentRadar

ar = AgentRadar(
    api_key="ar_live_your_key_here",
    endpoint="https://api.agent-radar.in",
    include_payloads=True,
)

SCENARIOS = [
    "successful_support",
    "failed_tool_call",
    "llm_exception",
    "multi_tool",
    "slow_run",
]


def run_scenario(scenario: str) -> None:
    print(f"  Running scenario: {scenario}")

    if scenario == "successful_support":
        with ar.start_run("CustomerSupportAgent", input={"question": "Track my order"}) as run:
            run.log_llm_call(model_name="sim-model", provider="simulator", duration_ms=400.0)
            with run.track_tool("track_order", input={"id": "ORD-001"}) as tool:
                time.sleep(0.05)
                tool.set_output({"status": "delivered"})
            run.log_llm_call(model_name="sim-model", provider="simulator", duration_ms=300.0)

    elif scenario == "failed_tool_call":
        with ar.start_run("OrderAgent", input={"order_id": "ORD-999"}) as run:
            run.log_tool_call(name="fetch_order", input={"id": "ORD-999"})
            run.log_error(
                error_type="ToolError",
                error_message="Order ORD-999 not found in database.",
                name="fetch_order",
            )

    elif scenario == "llm_exception":
        try:
            with ar.start_run("AnalysisAgent") as run:
                run.log_llm_call(model_name="sim-model", provider="simulator", duration_ms=200.0)
                raise RuntimeError("Simulated LLM rate-limit error")
        except RuntimeError:
            pass  # SDK already recorded the error and finished the run as failed

    elif scenario == "multi_tool":
        tools = ["search_db", "fetch_user", "calculate_price", "send_email"]
        with ar.start_run("WorkflowAgent", input={"task": "process_order"}) as run:
            for tool_name in tools:
                with run.track_tool(tool_name, input={"step": tool_name}) as tool:
                    time.sleep(0.01)
                    tool.set_output({"ok": True})

    elif scenario == "slow_run":
        with ar.start_run("SlowAgent", input={"query": "complex analysis"}) as run:
            run.log_llm_call(model_name="big-model", provider="simulator", duration_ms=3500.0)
            run.log_tool_call(name="heavy_computation")
            time.sleep(0.05)  # simulate real wait
            run.log_tool_result(name="heavy_computation", output={"result": 42}, duration_ms=2000.0)
            run.log_llm_call(model_name="big-model", provider="simulator", duration_ms=2200.0)


if __name__ == "__main__":
    print("AgentRadar Simulated Agent Demo")
    print("=" * 40)
    for s in SCENARIOS:
        try:
            run_scenario(s)
            print(f"  ✓ {s} completed")
        except Exception as e:
            print(f"  ✗ {s} error: {e}")
    print("\nAll scenarios complete. Check your AgentRadar dashboard!")
