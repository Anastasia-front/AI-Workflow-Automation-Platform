from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai import AIService
from app.services.embedding import EmbeddingService
from app.services.provider_config import ProviderConfigService, provider_config


async def load_provider_config(db: AsyncSession, user_id: int | None = None) -> None:
    await provider_config.load_from_db(db, user_id)


async def _resolve_config(db: AsyncSession, user_id: int | None) -> ProviderConfigService:
    """Build a task-scoped config instead of mutating the shared singleton,
    so this task's user can't have its credentials clobbered by another
    task loading a different user's config into shared state."""
    config = ProviderConfigService()
    await config.load_from_db(db, user_id)
    return config


async def resolve_ai_service(db: AsyncSession, user_id: int | None = None) -> AIService:
    # Chain mode: falls through CHAT_PROVIDER_CHAIN (normally ending in
    # Ollama, which needs no key) when this user has no key of their own
    # for the default provider.
    config = await _resolve_config(db, user_id)
    return AIService(chain=config.chat_chain())


async def resolve_embedding_service(
    db: AsyncSession, user_id: int | None = None
) -> EmbeddingService:
    config = await _resolve_config(db, user_id)
    return EmbeddingService(chain=config.embedding_chain())
