from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import DocumentStatus, EmbeddingStatus
from app.models import Document, DocumentChunk, Project


class DocumentRepository:

    async def create(
        self,
        db: AsyncSession,
        document: Document,
    ):
        db.add(document)
        await db.flush()

        return document

    async def get_by_id(
        self,
        db: AsyncSession,
        document_id: int,
    ):
        result = await db.execute(
            select(Document).where(
                Document.id == document_id
            )
        )

        return result.scalar_one_or_none()

    async def get_for_user(
        self,
        db: AsyncSession,
        document_id: int,
        user_id: int,
    ):
        result = await db.execute(
            select(Document)
            .join(
                Project,
                Project.id == Document.project_id,
            )
            .where(
                Document.id == document_id,
                Project.user_id == user_id,
            )
        )

        return result.scalar_one_or_none()

    async def list_for_project(
        self,
        db: AsyncSession,
        project_id: int,
    ):
        result = await db.execute(
            select(Document)
            .where(
                Document.project_id == project_id
            )
            .order_by(Document.id.desc())
        )

        return result.scalars().all()

    async def list_for_user(
        self,
        db: AsyncSession,
        user_id: int,
    ):
        result = await db.execute(
            select(Document)
            .join(
                Project,
                Project.id == Document.project_id,
            )
            .where(
                Project.user_id == user_id,
            )
            .order_by(Document.id.desc())
        )

        return result.scalars().all()

    async def delete(
        self,
        db: AsyncSession,
        document: Document,
    ):
        await db.delete(document)

        await db.flush()

    async def save_uploaded(
        self,
        db: AsyncSession,
        document: Document,
    ) -> Document:
        db.add(document)
        await db.commit()
        await db.refresh(document)
        return document

    async def queue_processing(
        self,
        db: AsyncSession,
        document: Document,
    ) -> Document:
        document.status = DocumentStatus.QUEUED
        document.processing_error = None
        await db.commit()
        await db.refresh(document)
        return document

    async def restore_uploaded(
        self,
        db: AsyncSession,
        document: Document,
    ) -> Document:
        document.status = DocumentStatus.UPLOADED
        await db.commit()
        await db.refresh(document)
        return document

    async def set_task_id(
        self,
        db: AsyncSession,
        document: Document,
        task_id: str,
    ) -> Document:
        document.celery_task_id = task_id
        await db.commit()
        await db.refresh(document)
        return document

    async def start_processing(
        self,
        db: AsyncSession,
        document: Document,
        started_at: datetime,
    ) -> None:
        if document.status in (DocumentStatus.CANCELLING, DocumentStatus.CANCELLED):
            return
        document.status = DocumentStatus.PROCESSING
        document.processing_started_at = started_at
        document.embedding_status = EmbeddingStatus.PROCESSING
        await db.flush()

    async def complete_processing(
        self,
        db: AsyncSession,
        document: Document,
        text: str,
        finished_at: datetime,
        duration_ms: int,
        embedding_provider: str,
        embedding_model: str,
        embedding_dimensions: int,
    ) -> Document:
        if document.status == DocumentStatus.CANCELLED:
            await db.refresh(document)
            return document
        document.text = text
        document.status = DocumentStatus.INDEXED
        document.embedding_status = EmbeddingStatus.COMPLETED
        document.embedding_provider = embedding_provider
        document.embedding_model = embedding_model
        document.embedding_dimensions = embedding_dimensions
        document.embeddings_updated_at = finished_at
        document.processing_finished_at = finished_at
        document.processing_duration_ms = duration_ms
        await db.commit()
        await db.refresh(document)
        return document

    async def mark_embeddings_current(
        self,
        db: AsyncSession,
        document: Document,
        *,
        provider: str,
        model_name: str,
        dimensions: int,
        updated_at: datetime,
    ) -> Document:
        document.embedding_status = EmbeddingStatus.COMPLETED
        document.embedding_provider = provider
        document.embedding_model = model_name
        document.embedding_dimensions = dimensions
        document.embeddings_updated_at = updated_at
        document.processing_error = None
        document.celery_task_id = None
        await db.commit()
        await db.refresh(document)
        return document

    async def mark_project_embeddings_current(
        self,
        db: AsyncSession,
        *,
        project_id: int,
        provider: str,
        model_name: str,
        dimensions: int,
        updated_at: datetime,
    ) -> list[Document]:
        result = await db.execute(
            select(Document).where(
                Document.project_id == project_id,
                Document.text.is_not(None),
                exists().where(DocumentChunk.document_id == Document.id),
            )
        )
        documents = list(result.scalars().all())

        for document in documents:
            document.embedding_status = EmbeddingStatus.COMPLETED
            document.embedding_provider = provider
            document.embedding_model = model_name
            document.embedding_dimensions = dimensions
            document.embeddings_updated_at = updated_at
            document.processing_error = None

        await db.commit()
        return documents

    async def fail_processing(
        self,
        db: AsyncSession,
        document: Document,
        error: str | None = None,
    ) -> Document:
        # Callers typically reach this right after a `db.rollback()` (see
        # DocumentService.process()'s except block), which expires every
        # attribute on tracked objects, not just on commit. Reading
        # `document.status` below would otherwise trigger an implicit lazy
        # reload outside of an awaited call chain, raising
        # sqlalchemy.exc.MissingGreenlet instead of failing the document
        # cleanly. Refresh explicitly first so the attribute access is safe.
        await db.refresh(document)
        if document.status == DocumentStatus.CANCELLED:
            return document
        document.status = DocumentStatus.FAILED
        document.embedding_status = EmbeddingStatus.FAILED
        document.processing_error = error
        await db.commit()
        await db.refresh(document)
        return document

    async def cancel_processing(
        self,
        db: AsyncSession,
        document: Document,
    ) -> Document:
        document.status = DocumentStatus.CANCELLED
        document.embedding_status = EmbeddingStatus.CANCELLED
        await db.commit()
        await db.refresh(document)
        return document

    async def rollback(self, db: AsyncSession) -> None:
        await db.rollback()
