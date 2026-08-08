"""Shared request/response translation for OpenAI-compatible chat-completions APIs.

OpenRouter and Groq both expose the same `tools` / `tool_calls` wire shape as
OpenAI's Chat Completions API, so the translation logic lives here once.
"""

import json
import uuid

from app.services.ai.tool_types import ChatResult, ToolCall, ToolSchema


def to_openai_tool(tool: ToolSchema) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def to_openai_messages(messages: list[dict]) -> list[dict]:
    converted = []
    for message in messages:
        if message["role"] == "assistant" and message.get("tool_calls"):
            converted.append(
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(call["arguments"]),
                            },
                        }
                        for call in message["tool_calls"]
                    ],
                }
            )
        elif message["role"] == "tool":
            converted.append(
                {
                    "role": "tool",
                    "tool_call_id": message["tool_call_id"],
                    "content": message["content"],
                }
            )
        else:
            converted.append(message)
    return converted


def from_openai_message(message: dict) -> ChatResult:
    raw_tool_calls = message.get("tool_calls") or []
    tool_calls = []
    for call in raw_tool_calls:
        function = call["function"]
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            arguments = {}
        tool_calls.append(
            ToolCall(
                id=call.get("id") or str(uuid.uuid4()),
                name=function["name"],
                arguments=arguments,
            )
        )
    return ChatResult(content=message.get("content"), tool_calls=tool_calls)
