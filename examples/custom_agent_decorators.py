"""Custom plain-Python agent tracing with @agent and @tool decorators.

Requirements:
    pip install agentradar-sdk

Run:
    python examples/custom_agent_decorators.py
"""

import os
import agentradar
from agentradar import agent, tool

# 1. Initialize AgentRadar
agentradar.init(
    api_key=os.getenv("AGENTRADAR_API_KEY", "ar_live_your_key_here"),
    service_name="custom-math-agent",
)

# 2. Decorate your custom tools and agent functions
@tool("calculator")
def multiply(a: float, b: float) -> float:
    """A simple tool that multiplies two numbers."""
    return a * b

@agent("MathAssistant")
def run_assistant(x: float, y: float) -> str:
    """The top-level agent execution."""
    product = multiply(x, y)
    return f"The product of {x} and {y} is {product}."

if __name__ == "__main__":
    output = run_assistant(6.5, 4.0)
    print("Agent output:", output)
    agentradar.flush()
