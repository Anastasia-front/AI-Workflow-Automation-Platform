import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core import settings
from app.services.ai.errors import (
    AllProvidersFailedError,
    ProviderError,
    ProviderFailureSummary,
    ProviderUnavailableError,
    classify_provider_error,
)

logger = logging.getLogger(__name__)


@dataclass
class ProviderAttempt:
    provider: str
    model: str
    call: Callable[[], Awaitable]


@dataclass
class ProviderResult:
    value: object
    provider: str
    model: str
    fallback_used: bool
    attempts: list[ProviderFailureSummary]


class ProviderCircuitBreaker:
    def __init__(self) -> None:
        self._failures: dict[str, int] = {}
        self._cooldowns: dict[str, float] = {}

    def healthy(self, provider: str) -> bool:
        return self._cooldowns.get(provider, 0) <= time.monotonic()

    def success(self, provider: str) -> None:
        self._failures.pop(provider, None)
        self._cooldowns.pop(provider, None)

    def failure(self, provider: str) -> None:
        count = self._failures.get(provider, 0) + 1
        self._failures[provider] = count
        if count >= settings.PROVIDER_FAILURE_THRESHOLD:
            self._cooldowns[provider] = (
                time.monotonic() + settings.PROVIDER_COOLDOWN_SECONDS
            )
            self._failures[provider] = 0


chat_breaker = ProviderCircuitBreaker()
embedding_breaker = ProviderCircuitBreaker()


async def run_with_failover(
    attempts: list[ProviderAttempt],
    *,
    breaker: ProviderCircuitBreaker,
    operation: str,
    cancellation_check: Callable[[], Awaitable[bool]] | None = None,
) -> ProviderResult:
    failures: list[ProviderFailureSummary] = []
    failover_count = 0

    for attempt in attempts:
        if cancellation_check and await cancellation_check():
            raise ProviderUnavailableError("Request was cancelled.")

        if not breaker.healthy(attempt.provider):
            failures.append(
                ProviderFailureSummary(
                    provider=attempt.provider,
                    model=attempt.model,
                    category="circuit_open",
                )
            )
            continue

        for retry in range(settings.PROVIDER_MAX_RETRIES + 1):
            started = time.monotonic()
            try:
                value = await attempt.call()
                breaker.success(attempt.provider)
                logger.info(
                    "provider_request_succeeded",
                    extra={
                        "operation": operation,
                        "provider": attempt.provider,
                        "model": attempt.model,
                        "retry_count": retry,
                        "latency_seconds": round(time.monotonic() - started, 3),
                        "fallback_used": bool(failures),
                    },
                )
                return ProviderResult(
                    value=value,
                    provider=attempt.provider,
                    model=attempt.model,
                    fallback_used=bool(failures),
                    attempts=failures,
                )
            except Exception as exc:  # noqa: BLE001
                error = classify_provider_error(exc)
                logger.warning(
                    "provider_request_failed",
                    extra={
                        "operation": operation,
                        "provider": attempt.provider,
                        "model": attempt.model,
                        "category": error.category,
                        "status_code": error.status_code,
                        "retry_count": retry,
                    },
                )

                if not error.retryable:
                    break

                if isinstance(error, ProviderError) and error.category == "quota":
                    break

                if retry < settings.PROVIDER_MAX_RETRIES:
                    delay = error.retry_after
                    if delay is None:
                        delay = settings.PROVIDER_RETRY_BASE_DELAY_SECONDS * (2**retry)
                    await asyncio.sleep(min(delay, 5))
                    continue
                break

        breaker.failure(attempt.provider)
        failures.append(
            ProviderFailureSummary(
                provider=attempt.provider,
                model=attempt.model,
                category=error.category,
                status_code=error.status_code,
            )
        )
        failover_count += 1
        logger.info(
            "provider_failover_attempt",
            extra={
                "operation": operation,
                "provider": attempt.provider,
                "model": attempt.model,
                "category": error.category,
                "failover_attempts": failover_count,
            },
        )

    logger.error(
        "all_providers_failed",
        extra={"operation": operation, "failover_attempts": failover_count},
    )
    raise AllProvidersFailedError(failures)
