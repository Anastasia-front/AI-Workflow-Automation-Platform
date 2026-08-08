import json
import uuid
from typing import Any

import httpx

from app.core import settings
from app.services.ai.providers.base import AIProvider
from app.services.ai.tool_types import ChatResult, ToolCall, ToolSchema


class GeminiProvider(AIProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def chat(
        self,
        *,
        messages: list[dict],
        model: str,
    ) -> str:
        contents = [
            {
                "role": "user" if message["role"] != "assistant" else "model",
                "parts": [
                    {
                        "text": message["content"],
                    }
                ],
            }
            for message in messages
            if message["role"] != "system"
        ]

        system_instruction = None

        system_messages = [
            message["content"]
            for message in messages
            if message["role"] == "system"
        ]

        if system_messages:
            system_instruction = {
                "parts": [
                    {
                        "text": "\n\n".join(system_messages),
                    }
                ]
            }

        payload = {
            "contents": contents,
        }

        if system_instruction:
            payload["system_instruction"] = system_instruction

        async with httpx.AsyncClient(timeout=settings.PROVIDER_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self.base_url}/models/{model}:generateContent",
                params={
                    "key": self.api_key,
                },
                json=payload,
            )

            response.raise_for_status()
            data = response.json()

            return data["candidates"][0]["content"]["parts"][0]["text"]

    async def stream_chat(
        self,
        *,
        messages: list[dict],
        model: str,
    ):
        contents = [
            {
                "role": "user" if message["role"] != "assistant" else "model",
                "parts": [
                    {
                        "text": message["content"],
                    }
                ],
            }
            for message in messages
            if message["role"] != "system"
        ]

        system_messages = [
            message["content"]
            for message in messages
            if message["role"] == "system"
        ]

        payload = {
            "contents": contents,
        }

        if system_messages:
            payload["system_instruction"] = {
                "parts": [
                    {
                        "text": "\n\n".join(system_messages),
                    }
                ]
            }

        async with (
            httpx.AsyncClient(timeout=settings.PROVIDER_REQUEST_TIMEOUT_SECONDS) as client,
            client.stream(
                "POST",
                f"{self.base_url}/models/{model}:streamGenerateContent",
                params={
                    "key": self.api_key,
                    "alt": "sse",
                },
                json=payload,
            ) as response,
        ):
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = json.loads(line.removeprefix("data:").strip())
                for candidate in data.get("candidates", []):
                    for part in candidate.get("content", {}).get("parts", []):
                        text = part.get("text", "")
                        if text:
                            yield text

    async def chat_with_tools(
        self,
        *,
        messages: list[dict],
        model: str,
        tools: list[ToolSchema],
    ) -> ChatResult:
        contents, system_instruction = _to_gemini_contents(messages)

        payload: dict[str, Any] = {
            "contents": contents,
            "tools": [
                {
                    "function_declarations": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": _to_gemini_schema(tool.parameters),
                        }
                        for tool in tools
                    ]
                }
            ],
        }
        if system_instruction:
            payload["system_instruction"] = system_instruction

        async with httpx.AsyncClient(timeout=settings.PROVIDER_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self.base_url}/models/{model}:generateContent",
                params={
                    "key": self.api_key,
                },
                json=payload,
            )

            response.raise_for_status()
            data = response.json()

            parts = data["candidates"][0]["content"]["parts"]
            return _from_gemini_parts(parts)


def _to_gemini_contents(messages: list[dict]) -> tuple[list[dict], dict | None]:
    contents = []
    system_messages = []

    for message in messages:
        role = message["role"]

        if role == "system":
            system_messages.append(message["content"])
        elif role == "assistant" and message.get("tool_calls"):
            contents.append(
                {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {
                                "name": call["name"],
                                "args": call["arguments"],
                            }
                        }
                        for call in message["tool_calls"]
                    ],
                }
            )
        elif role == "tool":
            try:
                response_payload = json.loads(message["content"])
                if not isinstance(response_payload, dict):
                    response_payload = {"result": response_payload}
            except (TypeError, json.JSONDecodeError):
                response_payload = {"result": message["content"]}
            contents.append(
                {
                    "role": "function",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": message["name"],
                                "response": response_payload,
                            }
                        }
                    ],
                }
            )
        else:
            contents.append(
                {
                    "role": "user" if role != "assistant" else "model",
                    "parts": [{"text": message["content"]}],
                }
            )

    system_instruction = None
    if system_messages:
        system_instruction = {"parts": [{"text": "\n\n".join(system_messages)}]}

    return contents, system_instruction


def _to_gemini_schema(schema: dict) -> dict:
    """Best-effort conversion of a JSON Schema (as produced by pydantic) to
    Gemini's OpenAPI-subset schema format: uppercase `type`, dropped keys
    Gemini doesn't understand (e.g. `title`, `additionalProperties`)."""
    if not isinstance(schema, dict):
        return schema

    converted: dict[str, Any] = {}
    for key, value in schema.items():
        if key in ("title", "additionalProperties"):
            continue
        if key == "type" and isinstance(value, str):
            converted[key] = value.upper()
        elif key == "properties" and isinstance(value, dict):
            converted[key] = {name: _to_gemini_schema(prop) for name, prop in value.items()}
        elif key == "items" and isinstance(value, dict):
            converted[key] = _to_gemini_schema(value)
        else:
            converted[key] = value
    return converted


def _from_gemini_parts(parts: list[dict]) -> ChatResult:
    text_parts = []
    tool_calls = []

    for part in parts:
        if "text" in part:
            text_parts.append(part["text"])
        elif "functionCall" in part:
            call = part["functionCall"]
            tool_calls.append(
                ToolCall(
                    id=str(uuid.uuid4()),
                    name=call["name"],
                    arguments=call.get("args") or {},
                )
            )

    return ChatResult(content="\n".join(text_parts) if text_parts else None, tool_calls=tool_calls)
