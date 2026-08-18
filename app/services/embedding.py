import asyncio
import logging

import httpx
from fastapi import HTTPException, status

from app.core import TRANSIENT_EMBEDDING_STATUS_CODES, settings
from app.enums import EmbeddingProvider
from app.services.ai.failover import (
    ProviderAttempt,
    embedding_breaker,
    run_with_failover,
)
from app.services.provider_config import provider_config

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(
        self,
        provider: EmbeddingProvider | None = None,
        model_name: str | None = None,
        dimensions: int | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        chain: list | None = None,
    ):
        # See AIService for why `chain` exists: pass a caller-resolved
        # (e.g. per-user) provider chain to avoid falling back to the
        # shared `provider_config` singleton.
        self._chain = chain
        config = chain[0] if chain and provider is None else provider_config.embeddings
        if dimensions is None:
            dimensions = config.dimensions

        if dimensions <= 0:
            raise ValueError("dimensions must be greater than 0")

        self.fixed_provider = provider
        self.provider = (provider or config.provider).lower()
        self.model_name = model_name or config.model
        self._dimensions = dimensions
        self.base_url = (base_url or config.base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else config.api_key

    # expose read-only API
    # but keep internal mutability control
    # avoids accidental runtime reconfiguration bugs
    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed_text(
        self,
        text: str,
    ) -> list[float]:
        if not text.strip():
            return [0.0] * self.dimensions

        if self.fixed_provider is None:
            return await self._embed_text_with_failover(text)

        try:
            if self.provider == EmbeddingProvider.OLLAMA:
                return await self._embed_ollama(text)

            if self.provider == EmbeddingProvider.OPENROUTER:
                return await self._embed_openrouter(text)

            if self.provider == EmbeddingProvider.GEMINI:
                return await self._embed_gemini(text)

            raise ValueError(f"Unsupported embedding provider: {self.provider}")
        except HTTPException:
            raise
        except httpx.HTTPStatusError as exc:
            raise self._provider_unavailable(exc) from exc
        except httpx.HTTPError as exc:
            raise self._provider_unavailable(exc) from exc

    async def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        if self.fixed_provider is None:
            return await self._embed_texts_with_failover(texts)

        vectors = []

        for text in texts:
            vector = await self.embed_text(text)
            vectors.append(vector)

            await asyncio.sleep(0.2)

        return vectors

    async def _embed_text_with_failover(self, text: str) -> list[float]:
        result = await run_with_failover(
            await self._embedding_attempts(
                lambda service: service._embed_text_fixed(text)
            ),
            breaker=embedding_breaker,
            operation="embedding",
        )
        self.provider = result.provider
        self.model_name = result.model
        return result.value

    async def _embed_texts_with_failover(self, texts: list[str]) -> list[list[float]]:
        result = await run_with_failover(
            await self._embedding_attempts(
                lambda service: service._embed_texts_fixed(texts)
            ),
            breaker=embedding_breaker,
            operation="embedding_batch",
        )
        self.provider = result.provider
        self.model_name = result.model
        return result.value

    async def _embedding_attempts(self, call_factory) -> list[ProviderAttempt]:
        attempts = []
        skipped = []
        chain = self._chain if self._chain is not None else provider_config.embedding_chain()
        for config in chain:
            if not config.model:
                skipped.append((config.provider.value, "no model configured"))
                continue
            if config.provider != EmbeddingProvider.OLLAMA and not config.api_key:
                skipped.append((config.provider.value, "no API key configured"))
                continue
            if (
                config.provider == EmbeddingProvider.OLLAMA
                and not await self._ollama_available(config)
            ):
                skipped.append((config.provider.value, f"unreachable at {config.base_url}"))
                continue
            service = EmbeddingService(
                provider=config.provider,
                model_name=config.model,
                dimensions=config.dimensions,
                base_url=config.base_url,
                api_key=config.api_key,
            )
            attempts.append(
                ProviderAttempt(
                    provider=config.provider.value,
                    model=config.model,
                    call=lambda service=service: call_factory(service),
                )
            )
        if not attempts:
            logger.warning("no_embedding_provider_available", extra={"skipped": skipped})
        return attempts

    async def _embed_text_fixed(self, text: str) -> list[float]:
        if self.provider == EmbeddingProvider.OLLAMA:
            return await self._embed_ollama(text)
        if self.provider == EmbeddingProvider.OPENROUTER:
            return await self._embed_openrouter(text)
        if self.provider == EmbeddingProvider.GEMINI:
            return await self._embed_gemini(text)
        raise ValueError(f"Unsupported embedding provider: {self.provider}")

    async def _embed_texts_fixed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vectors.append(await self._embed_text_fixed(text))
            await asyncio.sleep(0.2)
        return vectors

    async def _ollama_available(self, config) -> bool:
        if not config.base_url:
            return False
        try:
            # See AIService._ollama_available: a tight timeout here can
            # falsely exclude a cold/slow (but working) Ollama instance,
            # silently and with no recorded attempt.
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

    async def _embed_ollama(
        self,
        text: str,
    ) -> list[float]:
        async with httpx.AsyncClient(
            timeout=settings.PROVIDER_REQUEST_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": self.model_name,
                    "prompt": text,
                },
            )

            response.raise_for_status()
            data = response.json()

            return data["embedding"]

    async def _embed_openrouter(
        self,
        text: str,
    ) -> list[float]:
        async with httpx.AsyncClient(
            timeout=settings.PROVIDER_REQUEST_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model_name,
                    "input": text,
                    "dimensions": self.dimensions,
                },
            )

            response.raise_for_status()
            data = response.json()

            return data["data"][0]["embedding"]

    async def _embed_gemini(
        self,
        text: str,
    ) -> list[float]:
        last_error = None

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    timeout=settings.PROVIDER_REQUEST_TIMEOUT_SECONDS
                ) as client:
                    response = await client.post(
                        f"{self.base_url}/models/{self.model_name}:embedContent",
                        params={
                            "key": self.api_key,
                        },
                        json={
                            "content": {
                                "parts": [
                                    {
                                        "text": text,
                                    }
                                ]
                            },
                            "outputDimensionality": self.dimensions,
                        },
                    )

                    response.raise_for_status()
                    data = response.json()

                    return data["embedding"]["values"]

            except httpx.HTTPStatusError as exc:
                last_error = exc

                if exc.response.status_code in TRANSIENT_EMBEDDING_STATUS_CODES:
                    await asyncio.sleep(2**attempt)
                    continue

                raise

            except httpx.HTTPError as exc:
                last_error = exc
                await asyncio.sleep(2**attempt)
                continue

        raise last_error

    def _provider_unavailable(self, exc: httpx.HTTPError) -> HTTPException:
        provider = (
            self.provider.value if hasattr(self.provider, "value") else self.provider
        )

        if isinstance(exc, httpx.HTTPStatusError):
            detail = (
                f"{provider} embedding provider returned "
                f"{exc.response.status_code} {exc.response.reason_phrase}. "
                "Check the embedding provider API key, model, and API access."
            )
        else:
            detail = (
                f"{provider} embedding provider could not be reached. "
                "Check the embedding provider base URL and network access."
            )

        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        )
