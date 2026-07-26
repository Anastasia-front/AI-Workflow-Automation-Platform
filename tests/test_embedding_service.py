from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException, status

from app.dependencies import get_document_repository
from app.enums import DocumentStatus, EmbeddingProvider, EmbeddingStatus
from app.services.embedding import EmbeddingService
from app.services.embedding_management import EmbeddingManagementService


class FakeAsyncClient:
    def __init__(self, *, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        request = httpx.Request("POST", "https://example.test/embed")
        return httpx.Response(
            status_code=status.HTTP_400_BAD_REQUEST,
            request=request,
            json={"error": {"message": "API key forbidden"}},
        )


class FailingAsyncClient(FakeAsyncClient):
    async def post(self, *args, **kwargs):
        raise httpx.ConnectError("connection refused")


@pytest.mark.asyncio
async def test_gemini_forbidden_is_reported_as_service_unavailable(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = EmbeddingService(
        provider=EmbeddingProvider.GEMINI,
        model_name="gemini-embedding-001",
        dimensions=768,
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="bad-key",
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.embed_text("question")

    assert exc_info.value.status_code == 503
    assert "gemini embedding provider returned 403 Forbidden" in exc_info.value.detail
    assert "API key" in exc_info.value.detail
    assert "bad-key" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_embedding_network_error_is_reported_as_service_unavailable(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FailingAsyncClient)

    service = EmbeddingService(
        provider=EmbeddingProvider.GEMINI,
        model_name="gemini-embedding-001",
        dimensions=768,
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="key",
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.embed_text("question")

    assert exc_info.value.status_code == 503
    assert "gemini embedding provider could not be reached" in exc_info.value.detail


@pytest.mark.asyncio
async def test_document_completion_stores_successful_embedding_metadata():
    db = AsyncMock()
    document = MagicMock(status=DocumentStatus.PROCESSING)
    finished_at = object()

    result = await get_document_repository().complete_processing(
        db=db,
        document=document,
        text="extracted text",
        finished_at=finished_at,
        duration_ms=123,
        embedding_provider="gemini",
        embedding_model="text-embedding-004",
        embedding_dimensions=768,
    )

    assert result is document
    assert document.status == DocumentStatus.INDEXED
    assert document.embedding_status == EmbeddingStatus.COMPLETED
    assert document.embedding_provider == "gemini"
    assert document.embedding_model == "text-embedding-004"
    assert document.embedding_dimensions == 768
    assert document.embeddings_updated_at is finished_at
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_project_embedding_sync_removes_dimension_mismatches_before_embedding():
    db = AsyncMock()
    chunks = MagicMock()
    chunks.list_missing_embeddings_for_project = AsyncMock(return_value=[])
    chunk_embeddings = MagicMock()
    chunk_embeddings.delete_dimension_mismatches_for_project = AsyncMock()
    embedding_service = MagicMock(
        provider="ollama",
        model_name="nomic-embed-text",
        dimensions=768,
    )
    service = EmbeddingManagementService(
        embedding_service=embedding_service,
        chunks=chunks,
        chunk_embeddings=chunk_embeddings,
    )

    created = await service.sync_project_embeddings(db=db, project_id=7)

    assert created == 0
    chunk_embeddings.delete_dimension_mismatches_for_project.assert_awaited_once_with(
        db=db,
        project_id=7,
        provider="ollama",
        model_name="nomic-embed-text",
        dimensions=768,
    )
    chunks.list_missing_embeddings_for_project.assert_awaited_once_with(
        db=db,
        project_id=7,
        provider="ollama",
        model_name="nomic-embed-text",
    )
