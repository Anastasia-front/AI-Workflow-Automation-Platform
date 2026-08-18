import logging
from collections.abc import AsyncIterator
from types import SimpleNamespace

import httpx

from app.core import settings
from app.enums import ChatProvider
from app.services.ai.errors import (
    AllProvidersFailedError,
    ProviderFailureSummary,
    ProviderPartialGenerationError,
    classify_provider_error,
)
from app.services.ai.failover import ProviderAttempt, chat_breaker, run_with_failover
from app.services.ai.providers import (
    AIProvider,
    GeminiProvider,
    GroqAIProvider,
    OllamaProvider,
    OpenRouterProvider,
)
from app.services.ai.tool_types import ChatResult, ToolSchema
from app.services.provider_config import provider_config

logger = logging.getLogger(__name__)


class AIService:
    def __init__(
        self,
        provider: ChatProvider | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        chain: list | None = None,
    ):
        # `chain` is an explicit, caller-resolved list of candidate chat
        # configs (e.g. a specific user's provider chain) to fail over
        # across. When omitted, falls back to the shared `provider_config`
        # singleton's chain -- callers that need per-user isolation must
        # pass `chain` explicitly rather than relying on this default.
        self._chain = chain
        config = chain[0] if chain and provider is None else provider_config.chat

        self.fixed_provider = provider
        self.provider_name = provider or config.provider
        self.model = model or config.model
        self.fallback_model = fallback_model if fallback_model is not None else config.fallback_model
        self.base_url = base_url or config.base_url
        self.api_key = api_key if api_key is not None else config.api_key

        self.provider = self._build_provider()
        self.last_provider_used: str | None = None
        self.last_model_used: str | None = None
        self.last_fallback_used = False

    def _build_provider(
        self,
    ) -> AIProvider:
        if self.provider_name == ChatProvider.OLLAMA:
            return OllamaProvider(
                base_url=self.base_url,
            )

        if self.provider_name == ChatProvider.OPENROUTER:
            return OpenRouterProvider(
                api_key=self.api_key,
                base_url=self.base_url,
            )

        if self.provider_name == ChatProvider.GROQ:
            return GroqAIProvider(
                api_key=self.api_key,
                base_url=self.base_url,
            )

        if self.provider_name == ChatProvider.GEMINI:
            return GeminiProvider(
                api_key=self.api_key,
                base_url=self.base_url,
            )

        raise ValueError(f"Unsupported chat provider: {self.provider_name}")

    def _build_provider_for_config(self, config) -> AIProvider:
        provider_name = self.provider_name
        model = self.model
        base_url = self.base_url
        api_key = self.api_key
        self.provider_name = config.provider
        self.model = config.model
        self.base_url = config.base_url
        self.api_key = config.api_key
        try:
            return self._build_provider()
        finally:
            self.provider_name = provider_name
            self.model = model
            self.base_url = base_url
            self.api_key = api_key

    async def _available_chat_configs(self) -> list:
        if self.fixed_provider:
            if not self.model:
                return []
            if self.fixed_provider != ChatProvider.OLLAMA and not self.api_key:
                return []
            config = SimpleNamespace(
                provider=self.fixed_provider,
                model=self.model,
                base_url=self.base_url,
                api_key=self.api_key,
            )
            if self.fixed_provider == ChatProvider.OLLAMA and not await self._ollama_available(config):
                return []
            return [config]

        configs = self._chain if self._chain is not None else provider_config.chat_chain(self.fixed_provider)
        available = []
        skipped = []
        for config in configs:
            if not config.model:
                skipped.append((config.provider.value, "no model configured"))
                continue
            if config.provider != ChatProvider.OLLAMA and not config.api_key:
                skipped.append((config.provider.value, "no API key configured"))
                continue
            if config.provider == ChatProvider.OLLAMA and not await self._ollama_available(config):
                skipped.append((config.provider.value, f"unreachable at {config.base_url}"))
                continue
            available.append(config)
        if not available:
            logger.warning("no_chat_provider_available", extra={"skipped": skipped})
        return available

    async def _ollama_available(self, config) -> bool:
        if not config.base_url:
            return False
        try:
            # Ollama can be slow to answer even /api/tags while it's cold-
            # loading a model on first use, so this uses the same generous
            # timeout as an actual provider request rather than a tight
            # "quick ping" one -- a too-tight timeout here silently drops
            # Ollama out of the candidate list with no attempt recorded,
            # which is indistinguishable from it being genuinely down.
            async with httpx.AsyncClient(timeout=settings.PROVIDER_REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(f"{config.base_url.rstrip('/')}/api/tags")
                response.raise_for_status()
                return True
        except httpx.HTTPError as exc:
            logger.warning(
                "ollama_unavailable",
                extra={"base_url": config.base_url, "error": str(exc)},
            )
            return False

    async def generate_chat_response(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> str:
        used_model = model or self.model

        prepared_messages = messages

        if system_prompt:
            prepared_messages = [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                *messages,
            ]

        attempts = []
        for config in await self._available_chat_configs():
            model_name = used_model if config.provider == self.provider_name else config.model
            provider = self._build_provider_for_config(config)
            attempts.append(
                ProviderAttempt(
                    provider=config.provider.value,
                    model=model_name,
                    call=lambda provider=provider, model_name=model_name: provider.chat(
                        messages=prepared_messages,
                        model=model_name,
                    ),
                )
            )

        result = await run_with_failover(
            attempts,
            breaker=chat_breaker,
            operation="chat",
        )
        self.last_provider_used = result.provider
        self.last_model_used = result.model
        self.last_fallback_used = result.fallback_used
        return result.value

    async def generate_tool_call(
        self,
        messages: list[dict],
        *,
        tools: list[ToolSchema],
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> ChatResult:
        """Ask the model to either answer directly or call one of `tools`.

        Not every configured provider supports native tool calling, so this
        walks the same provider chain as `generate_chat_response` but skips
        (rather than fails over from) providers whose `chat_with_tools` is
        unimplemented, then applies the normal retry/circuit-breaker policy
        to the providers that do support it.
        """
        used_model = model or self.model

        prepared_messages = messages
        if system_prompt:
            prepared_messages = [
                {"role": "system", "content": system_prompt},
                *messages,
            ]

        attempts = []
        for config in await self._available_chat_configs():
            provider = self._build_provider_for_config(config)
            if type(provider).chat_with_tools is AIProvider.chat_with_tools:
                continue
            model_name = used_model if config.provider == self.provider_name else config.model
            attempts.append(
                ProviderAttempt(
                    provider=config.provider.value,
                    model=model_name,
                    call=lambda provider=provider, model_name=model_name: provider.chat_with_tools(
                        messages=prepared_messages,
                        model=model_name,
                        tools=tools,
                    ),
                )
            )

        if not attempts:
            raise AllProvidersFailedError(
                [ProviderFailureSummary(provider="none", model=used_model, category="unsupported")]
            )

        result = await run_with_failover(
            attempts,
            breaker=chat_breaker,
            operation="chat_with_tools",
        )
        self.last_provider_used = result.provider
        self.last_model_used = result.model
        self.last_fallback_used = result.fallback_used
        return result.value

    async def stream_chat_response(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        used_model = model or self.model

        prepared_messages = messages

        if system_prompt:
            prepared_messages = [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                *messages,
            ]

        failures: list[ProviderFailureSummary] = []

        for config in await self._available_chat_configs():
            model_name = used_model if config.provider == self.provider_name else config.model
            output_started = False
            provider = self._build_provider_for_config(config)
            try:
                async for chunk in provider.stream_chat(
                    messages=prepared_messages,
                    model=model_name,
                ):
                    output_started = True
                    self.last_provider_used = config.provider.value
                    self.last_model_used = model_name
                    self.last_fallback_used = bool(failures)
                    yield chunk
                return
            except Exception as exc:
                error = classify_provider_error(exc)
                if output_started:
                    raise ProviderPartialGenerationError(
                        "Provider failed after streaming output started.",
                        status_code=error.status_code,
                    ) from exc
                failures.append(
                    ProviderFailureSummary(
                        provider=config.provider.value,
                        model=model_name,
                        category=error.category,
                        status_code=error.status_code,
                    )
                )

        raise AllProvidersFailedError(failures)
