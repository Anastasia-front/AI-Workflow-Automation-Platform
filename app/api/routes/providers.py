from fastapi import APIRouter, Query

from app.dependencies import CurrentUserDep, DbSessionDep
from app.enums import ChatProvider, EmbeddingProvider
from app.schemas.provider import (
    ChatProviderConfigResponse,
    ChatProviderConfigUpdate,
    EmbeddingProviderConfigResponse,
    EmbeddingProviderConfigUpdate,
    ProviderConfigResponse,
    ProviderHealthResponse,
    ProvidersResponse,
)
from app.services.provider_config import provider_config

router = APIRouter()


@router.get("", response_model=ProvidersResponse)
async def list_providers(
    db: DbSessionDep,
    _user: CurrentUserDep,
):
    return await provider_config.synced_list_providers(db)


@router.get("/config", response_model=ProviderConfigResponse)
async def get_provider_config(
    db: DbSessionDep,
    _user: CurrentUserDep,
):
    return await provider_config.synced_current_config(db)


@router.patch("/chat/defaults", response_model=ChatProviderConfigResponse)
async def update_chat_defaults(
    payload: ChatProviderConfigUpdate,
    db: DbSessionDep,
    _user: CurrentUserDep,
):
    return await provider_config.synced_update_chat(db, payload)


@router.patch("/embeddings/defaults", response_model=EmbeddingProviderConfigResponse)
async def update_embedding_defaults(
    payload: EmbeddingProviderConfigUpdate,
    db: DbSessionDep,
    _user: CurrentUserDep,
):
    return await provider_config.synced_update_embeddings(db, payload)


@router.get("/chat/{provider}/health", response_model=ProviderHealthResponse)
async def check_chat_provider_health(
    provider: ChatProvider,
    db: DbSessionDep,
    _user: CurrentUserDep,
    model: str | None = Query(default=None),
):
    return await provider_config.check_chat_health(
        db=db,
        provider=provider,
        model=model,
    )


@router.get("/embeddings/{provider}/health", response_model=ProviderHealthResponse)
async def check_embedding_provider_health(
    provider: EmbeddingProvider,
    db: DbSessionDep,
    _user: CurrentUserDep,
    model: str | None = Query(default=None),
    dimensions: int | None = Query(default=None),
):
    return await provider_config.check_embedding_health(
        db=db,
        provider=provider,
        model=model,
        dimensions=dimensions,
    )
