"""Zero-code tracing with Anthropic and AgentRadar.

Requirements:
    pip install "agentradar-sdk[anthropic]" anthropic

Run:
    python examples/anthropic_agent.py
"""

import os
import agentradar
from anthropic import Anthropic

# 1. Initialize AgentRadar zero-code tracing (auto-instruments Anthropic)
agentradar.init(
    api_key=os.getenv("AGENTRADAR_API_KEY", "ar_live_your_key_here"),
    service_name="anthropic-research-agent",
)

# 2. Use your existing Anthropic code without ANY wrappers or changes
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", "sk-ant-..."))

message = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=256,
    messages=[
        {"role": "user", "content": "Explain what distributed tracing is in 2 sentences."}
    ],
)

print("Agent response:")
print(message.content[0].text)

# 3. Flushes automatically at exit via atexit, or flush explicitly:
agentradar.flush()
