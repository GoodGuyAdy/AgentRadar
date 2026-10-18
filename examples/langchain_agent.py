"""Zero-code tracing with LangChain and AgentRadar.

Requirements:
    pip install "agentradar-sdk[langchain]" langchain langchain-openai

Run:
    python examples/langchain_agent.py
"""

import os
import agentradar

# 1. Initialize AgentRadar zero-code tracing (auto-instruments LangChain & LangGraph)
agentradar.init(
    api_key=os.getenv("AGENTRADAR_API_KEY", "ar_live_your_key_here"),
    service_name="langchain-qa-pipeline",
)

# 2. Use your existing LangChain chains, runnables, or agents as-is
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Any model provider works (e.g. OpenAI, Anthropic, Ollama, etc.)
# If using ChatOpenAI:
try:
    from langchain_openai import ChatOpenAI

    prompt = ChatPromptTemplate.from_template("Summarize this topic in 3 bullets: {topic}")
    model = ChatOpenAI(model="gpt-4o")
    chain = prompt | model | StrOutputParser()

    result = chain.invoke({"topic": "Agent observability and evaluation"})
    print("Chain result:")
    print(result)
except ImportError:
    print("To run with ChatOpenAI, install langchain-openai.")

# 3. Flushes automatically at exit via atexit
agentradar.flush()
