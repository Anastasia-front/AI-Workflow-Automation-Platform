import json
import logging
import uuid

import httpx

from app.core import settings
from app.services.ai.providers.base import AIProvider
from app.services.ai.tool_types import ChatResult, ToolCall, ToolSchema

logger = logging.getLogger(__name__)


def _raise_with_body(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        logger.warning(
            "ollama_http_error",
            extra={
                "url": str(response.request.url),
                "status_code": response.status_code,
                "body": response.text[:2000],
            },
        )
        raise


async def _raise_with_body_streamed(response: httpx.Response) -> None:
    if response.is_success:
        return
    await response.aread()
    _raise_with_body(response)


class OllamaProvider(AIProvider):
    def __init__(
        self,
        base_url: str,
    ):
        self.base_url = base_url.rstrip("/")

    async def chat(
        self,
        *,
        messages: list[dict],
        model: str,
    ) -> str:
        async with httpx.AsyncClient(timeout=settings.PROVIDER_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                },
            )

            _raise_with_body(response)
            data = response.json()

            return data["message"]["content"]

    async def stream_chat(
        self,
        *,
        messages: list[dict],
        model: str,
    ):
        async with httpx.AsyncClient(timeout=settings.PROVIDER_REQUEST_TIMEOUT_SECONDS) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                },
            ) as response:
                await _raise_with_body_streamed(response)
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content

    async def chat_with_tools(
        self,
        *,
        messages: list[dict],
        model: str,
        tools: list[ToolSchema],
    ) -> ChatResult:
        async with httpx.AsyncClient(timeout=settings.PROVIDER_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": model,
                    "messages": _to_ollama_messages(messages),
                    "tools": [_to_ollama_tool(tool) for tool in tools],
                    "stream": False,
                },
            )

            _raise_with_body(response)
            data = response.json()

            return _from_ollama_message(data["message"])


def _to_ollama_tool(tool: ToolSchema) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _to_ollama_messages(messages: list[dict]) -> list[dict]:
    # Ollama has no concept of a tool_call_id: it matches tool results back
    # to calls by function name and position, so those fields are dropped.
    converted = []
    for message in messages:
        if message["role"] == "assistant" and message.get("tool_calls"):
            converted.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": call["name"],
                                "arguments": call["arguments"],
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
                    "content": message["content"],
                }
            )
        else:
            converted.append(message)
    return converted


def _from_ollama_message(message: dict) -> ChatResult:
    raw_tool_calls = message.get("tool_calls") or []
    tool_calls = [
        ToolCall(
            id=str(uuid.uuid4()),
            name=call["function"]["name"],
            arguments=call["function"].get("arguments") or {},
        )
        for call in raw_tool_calls
    ]
    return ChatResult(content=message.get("content"), tool_calls=tool_calls)
