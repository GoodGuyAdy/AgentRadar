"""Asynchronous agent example using AsyncAgentRadar."""
# Run: python examples/async_agent.py

import asyncio
from agentradar import AsyncAgentRadar

async def main():
    async with AsyncAgentRadar(
        api_key="ar_live_your_key_here",
        endpoint="https://api.agent-radar.in",
        include_payloads=True,
    ) as ar:
        # Check health
        health = await ar.check_health()
        print(f"AgentRadar backend status: {health.status} (v{health.version})")

        # Run an async agent workflow
        async with ar.start_run(
            agent_name="AsyncSearchAgent",
            input={"search_term": "AI Observability"},
        ) as run:
            run.log_llm_call(
                model_name="gpt-4o-mini",
                provider="openai",
                duration_ms=250.0,
                token_usage={"prompt_tokens": 30, "completion_tokens": 10},
            )

            # Measure tool call
            with run.track_tool("vector_db_search", input={"query": "AI Observability"}) as tool:
                await asyncio.sleep(0.05)
                tool.set_output({"results_count": 5})

            print(f"Async run {run.run_id} finished successfully!")

if __name__ == "__main__":
    asyncio.run(main())
