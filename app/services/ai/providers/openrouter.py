import json

import httpx

from app.core import settings
from app.services.ai.providers._openai_compat import (
    from_openai_message,
    to_openai_messages,
    to_openai_tool,
)
from app.services.ai.providers.base import AIProvider
from app.services.ai.tool_types import ChatResult, ToolSchema


class OpenRouterProvider(AIProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def chat(
        self,
        *,
        messages: list[dict],
        model: str,
    ) -> str:
        async with httpx.AsyncClient(timeout=settings.PROVIDER_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                },
            )

            response.raise_for_status()
            data = response.json()

            return data["choices"][0]["message"]["content"]

    async def stream_chat(
        self,
        *,
        messages: list[dict],
        model: str,
    ):
        async with httpx.AsyncClient(timeout=settings.PROVIDER_REQUEST_TIMEOUT_SECONDS) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line.removeprefix("data:").strip()
                    if payload == "[DONE]":
                        break
                    data = json.loads(payload)
                    content = data["choices"][0].get("delta", {}).get("content", "")
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
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": to_openai_messages(messages),
                    "tools": [to_openai_tool(tool) for tool in tools],
                },
            )

            response.raise_for_status()
            data = response.json()

            return from_openai_message(data["choices"][0]["message"])
