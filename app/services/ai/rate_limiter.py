import logging
import time

import redis.asyncio as redis

from app.core import settings

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None


def _get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.CELERY_BROKER_URL, decode_responses=True
        )
    return _redis_client


async def check_rate_limit(provider: str) -> float | None:
    """Fixed-window request counter shared across workers via Redis.

    Returns the number of seconds to wait before retrying if the provider's
    per-minute request budget is exhausted, or None if the request may proceed.
    Fails open (returns None) if Redis is unreachable, since a local outage of
    the limiter must not block AI requests.
    """
    if not settings.PROVIDER_RATE_LIMIT_ENABLED:
        return None

    window = int(time.time() // 60)
    key = f"ai_provider_rate_limit:{provider}:{window}"

    try:
        client = _get_redis_client()
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, 60)

        if count > settings.PROVIDER_RATE_LIMIT_RPM:
            return 60 - (time.time() % 60)
        return None
    except redis.RedisError:
        logger.warning("rate_limiter_redis_unavailable", extra={"provider": provider})
        return None
