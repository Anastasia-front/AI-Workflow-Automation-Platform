from dataclasses import dataclass
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import CHAT_KIND, EMBEDDING_KIND, decrypt_secret, encrypt_secret, settings
from app.enums import ChatProvider, EmbeddingProvider
from app.models import ProviderConfig
from app.repositories import ProviderConfigRepository
from app.schemas import (
    ChatProviderConfigResponse,
    ChatProviderConfigUpdate,
    EmbeddingProviderConfigResponse,
    EmbeddingProviderConfigUpdate,
    ProviderConfigResponse,
    ProviderHealthResponse,
    ProvidersResponse,
    ProviderStatus,
)
from app.services.exceptions import InvalidProviderConfigurationError


@dataclass
class ChatProviderConfigState:
    provider: ChatProvider
    model: str
    fallback_model: str | None
    base_url: str
    api_key: str
    active: bool = False


@dataclass
class EmbeddingProviderConfigState:
    provider: EmbeddingProvider
    model: str
    dimensions: int
    base_url: str
    api_key: str
    active: bool = False


class ProviderConfigService:
    def __init__(
        self,
        provider_configs: ProviderConfigRepository | None = None,
    ):
        self.provider_configs = provider_configs or ProviderConfigRepository()
        self.chat_configs = {
            provider: ChatProviderConfigState(
                provider=provider,
                model=settings.CHAT_MODEL if provider == settings.CHAT_PROVIDER else "",
                fallback_model=(
                    settings.CHAT_FALLBACK_MODEL
                    if provider == settings.CHAT_PROVIDER
                    else None
                ),
                base_url=self._default_chat_base_url(provider),
                api_key=(
                    settings.CHAT_API_KEY if provider == settings.CHAT_PROVIDER else ""
                ),
                active=provider == settings.CHAT_PROVIDER,
            )
            for provider in ChatProvider
        }
        self.embedding_configs = {
            provider: EmbeddingProviderConfigState(
                provider=provider,
                model=(
                    settings.EMBEDDING_MODEL
                    if provider == settings.EMBEDDING_PROVIDER
                    else ""
                ),
                dimensions=settings.EMBEDDING_DIM,
                base_url=self._default_embedding_base_url(provider),
                api_key=(
                    settings.EMBEDDING_API_KEY
                    if provider == settings.EMBEDDING_PROVIDER
                    else ""
                ),
                active=provider == settings.EMBEDDING_PROVIDER,
            )
            for provider in EmbeddingProvider
        }

    @property
    def chat(self) -> ChatProviderConfigState:
        return next(config for config in self.chat_configs.values() if config.active)

    @property
    def embeddings(self) -> EmbeddingProviderConfigState:
        return next(
            config for config in self.embedding_configs.values() if config.active
        )

    def chat_chain(
        self,
        fixed_provider: ChatProvider | None = None,
    ) -> list[ChatProviderConfigState]:
        if fixed_provider:
            return [self.chat_configs[fixed_provider]]

        providers = self._parse_chain(settings.CHAT_PROVIDER_CHAIN, ChatProvider)
        active = next(
            (provider for provider in self.chat_configs if self.chat_configs[provider].active),
            None,
        )
        ordered = []
        if active is not None:
            ordered.append(self.chat_configs[active])
        ordered.extend(
            self.chat_configs[provider] for provider in providers if provider != active
        )
        return ordered

    def embedding_chain(
        self,
        fixed_provider: EmbeddingProvider | None = None,
    ) -> list[EmbeddingProviderConfigState]:
        if fixed_provider:
            return [self.embedding_configs[fixed_provider]]

        providers = self._parse_chain(
            settings.EMBEDDING_PROVIDER_CHAIN, EmbeddingProvider
        )
        active = next(
            (
                provider
                for provider in self.embedding_configs
                if self.embedding_configs[provider].active
            ),
            None,
        )
        ordered = []
        if active is not None:
            ordered.append(self.embedding_configs[active])
        ordered.extend(
            self.embedding_configs[provider] for provider in providers if provider != active
        )
        return ordered

    async def load_from_db(self, db: AsyncSession, user_id: int | None = None) -> None:
        """Load global defaults, then overlay this user's own overrides on top.

        A global default row (user_id IS NULL) only ever supplies the
        provider/model/base_url/active shape for users who haven't set up
        their own config -- its stored API key, if any, belongs to no one
        in particular and must never be handed to a different user. Only a
        row that actually belongs to `user_id` may contribute its key.
        """
        rows = await self.provider_configs.list_all(db, user_id)
        rows.sort(key=lambda row: row.user_id is not None)

        for row in rows:
            is_own_row = row.user_id == user_id
            api_key = decrypt_secret(row.encrypted_api_key) if is_own_row else ""

            if row.kind == CHAT_KIND:
                provider = ChatProvider(row.provider)
                self.chat_configs[provider] = ChatProviderConfigState(
                    provider=provider,
                    model=row.model,
                    fallback_model=row.fallback_model,
                    base_url=row.base_url,
                    api_key=api_key,
                    active=row.active,
                )
            elif row.kind == EMBEDDING_KIND:
                provider = EmbeddingProvider(row.provider)
                self.embedding_configs[provider] = EmbeddingProviderConfigState(
                    provider=provider,
                    model=row.model,
                    dimensions=row.dimensions or settings.EMBEDDING_DIM,
                    base_url=row.base_url,
                    api_key=api_key,
                    active=row.active,
                )

    async def seed_defaults(self, db: AsyncSession) -> None:
        changed = False

        for config in self.chat_configs.values():
            if not await self._get_row(db, CHAT_KIND, config.provider.value):
                await self.provider_configs.add(db, self._chat_row(config))
                changed = True

        for config in self.embedding_configs.values():
            if not await self._get_row(db, EMBEDDING_KIND, config.provider.value):
                await self.provider_configs.add(db, self._embedding_row(config))
                changed = True

        if changed:
            await self.provider_configs.commit(db)

    async def sync_settings_to_db(self, db: AsyncSession) -> None:
        await self._sync_chat_settings(db)
        await self._sync_embedding_settings(db)
        await self.provider_configs.commit(db)

    async def _sync_chat_settings(self, db: AsyncSession) -> None:
        provider = settings.CHAT_PROVIDER
        config = self.chat_configs[provider]
        config.model = settings.CHAT_MODEL or config.model
        config.fallback_model = settings.CHAT_FALLBACK_MODEL or None
        config.base_url = self._settings_chat_base_url(provider)
        if settings.CHAT_API_KEY:
            config.api_key = settings.CHAT_API_KEY

        for item in self.chat_configs.values():
            item.active = item.provider == provider

        for item in self.chat_configs.values():
            row = await self._get_row(db, CHAT_KIND, item.provider.value)
            if not row:
                await self.provider_configs.add(db, self._chat_row(item))
                continue

            row.active = item.active
            if item.provider == provider:
                row.model = item.model
                row.fallback_model = item.fallback_model
                row.base_url = item.base_url
                row.encrypted_api_key = encrypt_secret(item.api_key)
                row.dimensions = None

    async def _sync_embedding_settings(self, db: AsyncSession) -> None:
        provider = settings.EMBEDDING_PROVIDER
        config = self.embedding_configs[provider]
        config.model = settings.EMBEDDING_MODEL or config.model
        config.dimensions = settings.EMBEDDING_DIM
        config.base_url = self._settings_embedding_base_url(provider)
        if settings.EMBEDDING_API_KEY:
            config.api_key = settings.EMBEDDING_API_KEY

        for item in self.embedding_configs.values():
            item.active = item.provider == provider

        for item in self.embedding_configs.values():
            row = await self._get_row(db, EMBEDDING_KIND, item.provider.value)
            if not row:
                await self.provider_configs.add(db, self._embedding_row(item))
                continue

            row.active = item.active
            if item.provider == provider:
                row.model = item.model
                row.fallback_model = None
                row.base_url = item.base_url
                row.encrypted_api_key = encrypt_secret(item.api_key)
                row.dimensions = item.dimensions

    def list_providers(self) -> ProvidersResponse:
        return ProvidersResponse(
            chat=[
                ProviderStatus(
                    name=config.provider.value,
                    kind=CHAT_KIND,
                    active=config.active,
                    default_model=config.model,
                    base_url=config.base_url,
                    api_key_configured=bool(config.api_key),
                    supports_api_key=config.provider != ChatProvider.OLLAMA,
                )
                for config in self.chat_configs.values()
            ],
            embeddings=[
                ProviderStatus(
                    name=config.provider.value,
                    kind=EMBEDDING_KIND,
                    active=config.active,
                    default_model=config.model,
                    base_url=config.base_url,
                    api_key_configured=bool(config.api_key),
                    supports_api_key=config.provider != EmbeddingProvider.OLLAMA,
                )
                for config in self.embedding_configs.values()
            ],
            current=self.current_config(),
        )

    def current_config(self) -> ProviderConfigResponse:
        return ProviderConfigResponse(
            chat=ChatProviderConfigResponse(
                provider=self.chat.provider,
                model=self.chat.model,
                fallback_model=self.chat.fallback_model,
                base_url=self.chat.base_url,
                api_key_configured=bool(self.chat.api_key),
            ),
            embeddings=EmbeddingProviderConfigResponse(
                provider=self.embeddings.provider,
                model=self.embeddings.model,
                dimensions=self.embeddings.dimensions,
                base_url=self.embeddings.base_url,
                api_key_configured=bool(self.embeddings.api_key),
            ),
        )

    async def update_chat(
        self,
        db: AsyncSession,
        payload: ChatProviderConfigUpdate,
        user_id: int,
    ) -> ChatProviderConfigResponse:
        provider = payload.provider or self.chat.provider
        config = self.chat_configs[provider]

        if payload.model is not None:
            config.model = payload.model
        if payload.fallback_model is not None:
            config.fallback_model = payload.fallback_model or None
        if payload.base_url is not None:
            config.base_url = payload.base_url
        if payload.api_key is not None:
            config.api_key = payload.api_key

        for item in self.chat_configs.values():
            item.active = item.provider == provider

        await self._save_all_chat(db, user_id)
        return self.current_config().chat

    async def update_embeddings(
        self,
        db: AsyncSession,
        payload: EmbeddingProviderConfigUpdate,
        user_id: int,
    ) -> EmbeddingProviderConfigResponse:
        provider = payload.provider or self.embeddings.provider
        config = self.embedding_configs[provider]

        if payload.model is not None:
            config.model = payload.model
        if payload.dimensions is not None:
            if payload.dimensions <= 0:
                raise InvalidProviderConfigurationError(
                    "dimensions must be greater than 0"
                )
            config.dimensions = payload.dimensions
        if payload.base_url is not None:
            config.base_url = payload.base_url
        if payload.api_key is not None:
            config.api_key = payload.api_key

        for item in self.embedding_configs.values():
            item.active = item.provider == provider

        await self._save_all_embeddings(db, user_id)
        return self.current_config().embeddings

    async def synced_list_providers(
        self, db: AsyncSession, user_id: int
    ) -> ProvidersResponse:
        await self.load_from_db(db, user_id)
        return self.list_providers()

    async def synced_current_config(
        self, db: AsyncSession, user_id: int
    ) -> ProviderConfigResponse:
        await self.load_from_db(db, user_id)
        return self.current_config()

    async def synced_update_chat(
        self,
        db: AsyncSession,
        payload: ChatProviderConfigUpdate,
        user_id: int,
    ) -> ChatProviderConfigResponse:
        await self.load_from_db(db, user_id)
        return await self.update_chat(db, payload, user_id)

    async def synced_update_embeddings(
        self,
        db: AsyncSession,
        payload: EmbeddingProviderConfigUpdate,
        user_id: int,
    ) -> EmbeddingProviderConfigResponse:
        await self.load_from_db(db, user_id)
        return await self.update_embeddings(db, payload, user_id)

    async def check_chat_health(
        self,
        db: AsyncSession,
        *,
        provider: ChatProvider,
        model: str | None = None,
        user_id: int | None = None,
    ) -> ProviderHealthResponse:
        from app.services.ai import AIService

        await self.load_from_db(db, user_id)
        config = self.chat_configs[provider]
        model_name = model or config.model
        service = AIService(
            provider=provider,
            model=model_name,
            fallback_model=config.fallback_model,
            base_url=config.base_url,
            api_key=config.api_key,
        )

        started = perf_counter()
        try:
            await service.generate_chat_response(
                messages=[
                    {
                        "role": "user",
                        "content": "Health check. Reply with ok.",
                    }
                ],
                model=model_name,
            )
            healthy = True
            message = "Provider responded."
        except Exception as exc:  # noqa: BLE001
            healthy = False
            message = str(exc)

        return ProviderHealthResponse(
            provider=provider.value,
            kind=CHAT_KIND,
            model=model_name,
            healthy=healthy,
            message=message,
            latency_ms=self._elapsed_ms(started),
        )

    async def check_embedding_health(
        self,
        db: AsyncSession,
        *,
        provider: EmbeddingProvider,
        model: str | None = None,
        dimensions: int | None = None,
        user_id: int | None = None,
    ) -> ProviderHealthResponse:
        from app.services.embedding import EmbeddingService

        await self.load_from_db(db, user_id)
        config = self.embedding_configs[provider]
        model_name = model or config.model

        try:
            service = EmbeddingService(
                provider=provider,
                model_name=model_name,
                dimensions=dimensions if dimensions is not None else config.dimensions,
                base_url=config.base_url,
                api_key=config.api_key,
            )
        except ValueError as exc:
            raise InvalidProviderConfigurationError(str(exc)) from exc

        started = perf_counter()
        try:
            await service.embed_text("health check")
            healthy = True
            message = "Provider responded."
        except Exception as exc:  # noqa: BLE001
            healthy = False
            message = str(exc)

        return ProviderHealthResponse(
            provider=provider.value,
            kind=EMBEDDING_KIND,
            model=model_name,
            healthy=healthy,
            message=message,
            latency_ms=self._elapsed_ms(started),
        )

    async def _save_all_chat(self, db: AsyncSession, user_id: int) -> None:
        for config in self.chat_configs.values():
            row = await self._get_row(db, CHAT_KIND, config.provider.value, user_id)
            if not row:
                await self.provider_configs.add(db, self._chat_row(config, user_id))
            else:
                row.model = config.model
                row.fallback_model = config.fallback_model
                row.base_url = config.base_url
                row.encrypted_api_key = encrypt_secret(config.api_key)
                row.active = config.active
                row.dimensions = None

        await self.provider_configs.commit(db)

    async def _save_all_embeddings(self, db: AsyncSession, user_id: int) -> None:
        for config in self.embedding_configs.values():
            row = await self._get_row(db, EMBEDDING_KIND, config.provider.value, user_id)
            if not row:
                await self.provider_configs.add(db, self._embedding_row(config, user_id))
            else:
                row.model = config.model
                row.fallback_model = None
                row.base_url = config.base_url
                row.encrypted_api_key = encrypt_secret(config.api_key)
                row.active = config.active
                row.dimensions = config.dimensions

        await self.provider_configs.commit(db)

    async def _get_row(
        self,
        db: AsyncSession,
        kind: str,
        provider: str,
        user_id: int | None = None,
    ) -> ProviderConfig | None:
        """Write-target lookup: the exact row for (kind, provider, user_id),
        with no fallback to another user's or the global row."""
        return await self.provider_configs.get_own(db, kind, provider, user_id)

    def _chat_row(
        self, config: ChatProviderConfigState, user_id: int | None = None
    ) -> ProviderConfig:
        return ProviderConfig(
            user_id=user_id,
            kind=CHAT_KIND,
            provider=config.provider.value,
            model=config.model,
            fallback_model=config.fallback_model,
            base_url=config.base_url,
            encrypted_api_key=encrypt_secret(config.api_key),
            active=config.active,
            dimensions=None,
        )

    def _embedding_row(
        self, config: EmbeddingProviderConfigState, user_id: int | None = None
    ) -> ProviderConfig:
        return ProviderConfig(
            user_id=user_id,
            kind=EMBEDDING_KIND,
            provider=config.provider.value,
            model=config.model,
            fallback_model=None,
            base_url=config.base_url,
            encrypted_api_key=encrypt_secret(config.api_key),
            active=config.active,
            dimensions=config.dimensions,
        )

    def _default_chat_base_url(self, provider: ChatProvider) -> str:
        defaults = {
            # ChatProvider.OLLAMA: settings.CHAT_BASE_URL,
            ChatProvider.OLLAMA: "http://ollama.ai-platform.internal:11434",
            ChatProvider.OPENROUTER: "https://openrouter.ai/api/v1",
            ChatProvider.GROQ: "https://api.groq.com/openai/v1",
            ChatProvider.GEMINI: "https://generativelanguage.googleapis.com/v1beta",
        }
        return defaults[provider]

    def _settings_chat_base_url(self, provider: ChatProvider) -> str:
        if (
            provider == ChatProvider.OLLAMA
            or settings.CHAT_BASE_URL != "http://ollama.ai-platform.internal:11434"
        ):
            return settings.CHAT_BASE_URL
        return self._default_chat_base_url(provider)

    def _default_embedding_base_url(self, provider: EmbeddingProvider) -> str:
        defaults = {
            EmbeddingProvider.OLLAMA: "http://ollama.ai-platform.internal:11434",
            EmbeddingProvider.OPENROUTER: "https://openrouter.ai/api/v1",
            EmbeddingProvider.GEMINI: "https://generativelanguage.googleapis.com/v1beta",
        }
        return defaults[provider]

    def _settings_embedding_base_url(self, provider: EmbeddingProvider) -> str:
        if (
            provider == EmbeddingProvider.OLLAMA
            or settings.EMBEDDING_BASE_URL != "http://ollama.ai-platform.internal:11434"
        ):
            return settings.EMBEDDING_BASE_URL
        return self._default_embedding_base_url(provider)

    def _parse_chain(self, value: str, enum_type):
        providers = []
        seen = set()
        for item in value.split(","):
            name = item.strip().lower()
            if not name or name in seen:
                continue
            providers.append(enum_type(name))
            seen.add(name)
        return providers

    def _elapsed_ms(self, started: float) -> int:
        return int((perf_counter() - started) * 1000)


provider_config = ProviderConfigService()
