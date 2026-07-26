import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import (
    ALLOWED_CONTENT_TYPES,
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_SIZE,
)
from app.enums import DocumentStatus
from app.models import Document, DocumentChunk, Project
from app.repositories import (
    ChunkEmbeddingRepository,
    DocumentChunkRepository,
    DocumentRepository,
)
from app.schemas import DocumentProcessingResponse
from app.services.background_jobs import BackgroundJobService
from app.services.chunk import ChunkService
from app.services.embedding import EmbeddingService
from app.services.storage import LocalStorageService, StorageService

from .extractors import DEFAULT_EXTRACTORS, TextExtractor


class DocumentService:
    def __init__(
        self,
        storage: StorageService | None = None,
        documents: DocumentRepository | None = None,
        chunks: DocumentChunkRepository | None = None,
        chunk_embeddings: ChunkEmbeddingRepository | None = None,
        chunker: ChunkService | None = None,
        embeddings: EmbeddingService | None = None,
        extractors: tuple[TextExtractor, ...] = DEFAULT_EXTRACTORS,
    ):
        self.storage = storage or LocalStorageService()

        self.documents = documents or DocumentRepository()
        self.chunks = chunks or DocumentChunkRepository()
        self.chunk_embeddings = chunk_embeddings or ChunkEmbeddingRepository()
        self.chunker = chunker or ChunkService()
        self.embeddings = embeddings or EmbeddingService()

        self.extractors = extractors

    async def upload(
        self,
        db: AsyncSession,
        project: Project,
        file: UploadFile,
    ) -> Document:

        content = await file.read()

        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File is too large.",
            )

        original_filename = self._safe_filename(file.filename)
        extension = Path(original_filename).suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file extension.",
            )

        mime_type = (
            file.content_type
            or mimetypes.guess_type(original_filename)[0]
            or "application/octet-stream"
        )

        if mime_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type.",
            )

        stored_filename = self._stored_filename(original_filename)

        stored_path = await self.storage.save(
            filename=stored_filename,
            content=content,
        )

        document = Document(
            project_id=project.id,
            filename=original_filename,
            filepath=stored_path,
            mime_type=mime_type,
            file_size=len(content),
            status=DocumentStatus.UPLOADED,
        )

        return await self.documents.save_uploaded(db, document)

    async def process(
        self,
        db: AsyncSession,
        document: Document,
        chunk_size: int = 1000,
        overlap: int = 200,
    ) -> Document:

        started = datetime.now(timezone.utc)
        await self.documents.start_processing(db, document, started)

        try:
            text = await self.extract_text(document)

            chunk_objects = self.chunk_document(
                document=document,
                text=text,
                chunk_size=chunk_size,
                overlap=overlap,
            )

            await self.chunks.delete_for_document(db, document.id)

            await self.chunks.create_many(
                db,
                chunk_objects,
            )

            vectors = await self.embeddings.embed_texts(
                [chunk.text for chunk in chunk_objects]
            )

            await self.chunk_embeddings.create_for_chunks(
                db=db,
                chunks=chunk_objects,
                vectors=vectors,
                provider=self.embeddings.provider,
                model_name=self.embeddings.model_name,
                dimensions=self.embeddings.dimensions,
            )

            finished = datetime.now(timezone.utc)
            duration_ms = int(
                (finished - started).total_seconds() * 1000
            )

            return await self.documents.complete_processing(
                db=db,
                document=document,
                text=text,
                finished_at=finished,
                duration_ms=duration_ms,
                embedding_provider=self.embeddings.provider,
                embedding_model=self.embeddings.model_name,
                embedding_dimensions=self.embeddings.dimensions,
            )

        except Exception as exc:
            await self.documents.rollback(db)

            await self.documents.fail_processing(db, document, str(exc))

            raise

    async def extract_text(
        self,
        document: Document,
    ) -> str:

        file_bytes = await self.storage.read(document.filepath)

        for extractor in self.extractors:
            if extractor.supports(Path(document.filename)):
                return extractor.extract_bytes(
                    file_bytes=file_bytes,
                )

        raise ValueError(
            f"Unsupported document type: {document.filename}"
        )

    async def enqueue_processing(
        self,
        db: AsyncSession,
        document: Document,
        jobs: BackgroundJobService,
    ) -> Document:
        from app.tasks.documents import process_document_task

        if document.status in (
            DocumentStatus.QUEUED,
            DocumentStatus.PROCESSING,
            DocumentStatus.CANCELLING,
        ):
            return document

        await self.documents.queue_processing(db, document)

        try:
            task = jobs.enqueue(process_document_task, document.id)
        except HTTPException:
            await self.documents.restore_uploaded(db, document)
            raise

        return await self.documents.set_task_id(db, document, task.id)

    async def enqueue_processing_response(
        self,
        db: AsyncSession,
        document: Document,
        jobs: BackgroundJobService,
    ) -> DocumentProcessingResponse:
        document = await self.enqueue_processing(db, document, jobs)
        return await self.processing_response(db, document)

    async def cancel_processing(
        self,
        db: AsyncSession,
        document: Document,
        jobs: BackgroundJobService,
    ) -> DocumentProcessingResponse:
        if document.status in (
            DocumentStatus.QUEUED,
            DocumentStatus.PROCESSING,
            DocumentStatus.CANCELLING,
        ):
            document.status = DocumentStatus.CANCELLING
            await db.commit()
            await db.refresh(document)

            if document.celery_task_id:
                jobs.revoke(document.celery_task_id, terminate=True)

            document = await self.documents.cancel_processing(db, document)

        return await self.processing_response(db, document)

    async def retry_processing(
        self,
        db: AsyncSession,
        document: Document,
        jobs: BackgroundJobService,
    ) -> DocumentProcessingResponse:
        document.status = DocumentStatus.UPLOADED
        await db.commit()
        await db.refresh(document)

        document = await self.enqueue_processing(db, document, jobs)
        return await self.processing_response(db, document)

    async def delete(self, db: AsyncSession, document: Document) -> None:
        await self.documents.delete(db, document)
        await db.commit()

    async def processing_response(
        self,
        db: AsyncSession,
        document: Document,
    ) -> DocumentProcessingResponse:
        chunk_count = await self.chunks.count_for_document(db, document.id)

        return DocumentProcessingResponse(
            id=document.id,
            status=document.status,
            celery_task_id=document.celery_task_id,
            processing_started_at=document.processing_started_at,
            processing_finished_at=document.processing_finished_at,
            processing_duration_ms=document.processing_duration_ms,
            processing_error=document.processing_error,
            embedding_status=document.embedding_status,
            chunk_count=chunk_count,
        )

    def chunk_document(
        self,
        document: Document,
        text: str,
        chunk_size: int = 1000,
        overlap: int = 200,
    ) -> list[DocumentChunk]:

        return [
            DocumentChunk(
                document_id=document.id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                token_count=chunk.token_count,
            )
            for chunk in self.chunker.chunk(
                text=text,
                chunk_size=chunk_size,
                overlap=overlap,
            )
        ]

    def _safe_filename(
        self,
        filename: str | None,
    ) -> str:

        name = Path(filename or "document").name

        safe = re.sub(
            r"[^\w.\-]+",
            "_",
            name,
            flags=re.UNICODE,
        ).strip("._")

        return safe or "document"

    def _stored_filename(
        self,
        filename: str,
    ) -> str:

        return f"{uuid4()}{Path(filename).suffix.lower()}"
