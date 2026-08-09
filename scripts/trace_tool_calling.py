"""Manual trace script: exercises the real tool-calling + validation-retry
loop against a locally running Ollama, with full request/response logging.

Run:
    python scripts/trace_tool_calling.py

Requires Ollama running locally with a tool-capable model pulled
(default: qwen2.5:7b). Override with:
    OLLAMA_URL=http://localhost:11434 OLLAMA_MODEL=qwen2.5:7b python scripts/trace_tool_calling.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import httpx

from app.services.ai.providers.ollama import OllamaProvider
from app.services.workspace_tool_specs import WORKSPACE_TOOL_SPECS

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("trace")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


class LoggingOllamaProvider(OllamaProvider):
    """Same as OllamaProvider but prints the exact request/response JSON."""

    async def chat_with_tools(self, *, messages, model, tools):
        from app.services.ai.providers.ollama import (
            _to_ollama_messages,
            _to_ollama_tool,
        )

        payload = {
            "model": model,
            "messages": _to_ollama_messages(messages),
            "tools": [_to_ollama_tool(tool) for tool in tools],
            "stream": False,
        }
        log.info("\n>>> REQUEST to %s/api/chat", self.base_url)
        log.info(json.dumps(payload, indent=2))

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

        log.info("\n<<< RESPONSE")
        log.info(json.dumps(data, indent=2))

        from app.services.ai.providers.ollama import _from_ollama_message

        return _from_ollama_message(data["message"])


async def main() -> None:
    provider = LoggingOllamaProvider(base_url=OLLAMA_URL)

    # Only expose a couple of read-only tools that need no live DB, so this
    # script can run standalone without a database connection.
    schemas = [
        spec.to_schema()
        for spec in WORKSPACE_TOOL_SPECS
        if spec.name in ("list_workflows", "list_project_documents")
    ]

    system_prompt = (
        "You are the Workspace Agent for an AI automation platform project. "
        "Call a tool when the user's request maps to one of the available tools."
    )
    messages = [{"role": "user", "content": "List the workflows in this project."}]

    log.info("=== Turn 1: asking the model to pick a tool ===")
    result = await provider.chat_with_tools(
        messages=[{"role": "system", "content": system_prompt}, *messages],
        model=MODEL,
        tools=schemas,
    )

    log.info("\n=== Parsed ChatResult ===")
    log.info("content=%r", result.content)
    log.info("tool_calls=%r", result.tool_calls)

    if not result.tool_calls:
        log.info("\nModel did not call a tool -- nothing further to trace.")
        return

    tool_call = result.tool_calls[0]

    # Simulate a tool result without touching a real DB.
    fake_tool_result = {
        "tool": tool_call.name,
        "status": "completed",
        "data": {"workflows": [{"id": 1, "name": "Extract invoice fields", "status": "pending"}]},
        "message": None,
    }

    messages.append(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": tool_call.id, "name": tool_call.name, "arguments": tool_call.arguments}],
        }
    )
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_call.name,
            "content": json.dumps(fake_tool_result),
        }
    )

    log.info("\n=== Turn 2: feeding the tool result back for a final answer ===")
    result2 = await provider.chat_with_tools(
        messages=[{"role": "system", "content": system_prompt}, *messages],
        model=MODEL,
        tools=schemas,
    )
    log.info("\n=== Final ChatResult ===")
    log.info("content=%r", result2.content)
    log.info("tool_calls=%r", result2.tool_calls)


if __name__ == "__main__":
    asyncio.run(main())
