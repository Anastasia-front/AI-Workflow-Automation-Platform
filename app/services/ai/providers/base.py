from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.services.ai.tool_types import ChatResult, ToolSchema


class AIProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        *,
        messages: list[dict],
        model: str,
    ) -> str:
        raise NotImplementedError

    async def stream_chat(
        self,
        *,
        messages: list[dict],
        model: str,
    ) -> AsyncIterator[str]:
        yield await self.chat(messages=messages, model=model)

    async def chat_with_tools(
        self,
        *,
        messages: list[dict],
        model: str,
        tools: list[ToolSchema],
    ) -> ChatResult:
        raise NotImplementedError(f"{type(self).__name__} does not support tool calling")
