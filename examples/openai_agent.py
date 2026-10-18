"""Zero-code tracing with OpenAI and AgentRadar.

Requirements:
    pip install "agentradar-sdk[openai]" openai

Run:
    python examples/openai_agent.py
"""

import os
import agentradar
from openai import OpenAI

# 1. Initialize AgentRadar zero-code tracing (auto-instruments OpenAI)
agentradar.init(
    api_key=os.getenv("AGENTRADAR_API_KEY", "ar_live_your_key_here"),
    service_name="openai-support-agent",
    # include_payloads=False  # default: strips prompts/completions for privacy
)

# 2. Use your existing OpenAI code without ANY wrappers or changes
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "sk-..."))

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You are a concise customer service assistant."},
        {"role": "user", "content": "How do I reset my account password?"},
    ],
)

print("Agent response:")
print(response.choices[0].message.content)

# 3. Flushes automatically at exit via atexit, or you can flush manually:
agentradar.flush()
