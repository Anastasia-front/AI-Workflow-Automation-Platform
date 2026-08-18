import asyncio
import logging
import os
from datetime import datetime, timezone

from app.core.celery_app import celery_app
from app.core.celery_database import CelerySessionLocal, safe_database_url
from app.enums import EmbeddingStatus
from app.repositories import DocumentRepository, ProjectRepository
from app.services.embedding_management import (
    EmbeddingExecutionCancelled,
    EmbeddingManagementService,
)
from app.tasks.provider_config import resolve_embedding_service

logger = logging.getLogger(__name__)


def _log_task_start(task_name: str, task_id: str | None, item_id: int, session: object) -> None:
    logger.info(
        "Starting task=%s task_id=%s pid=%s item_id=%s db=%s loop_id=%s session_id=%s",
        task_name,
        task_id,
        os.getpid(),
        item_id,
        safe_database_url(),
        id(asyncio.get_running_loop()),
        id(session),
    )


async def _document_embedding_cancelled(
    document_id: int,
    documents: DocumentRepository | None = None,
) -> bool:
    documents = documents or DocumentRepository()
    async with CelerySessionLocal() as db:
        document = await documents.get_by_id(db, document_id)
        return document is None or document.embedding_status in (
            EmbeddingStatus.CANCELLING,
            EmbeddingStatus.CANCELLED,
        )


async def _project_embedding_cancelled(
    project_id: int,
    projects: ProjectRepository | None = None,
) -> bool:
    projects = projects or ProjectRepository()
    async with CelerySessionLocal() as db:
        project = await projects.get_by_id(db, project_id)
        return project is None or project.embedding_sync_status in (
            EmbeddingStatus.CANCELLING,
            EmbeddingStatus.CANCELLED,
        )


async def _rebuild_document_embeddings(
    document_id: int,
    task_id: str | None = None,
    force: bool = True,
    documents: DocumentRepository | None = None,
) -> None:
    documents = documents or DocumentRepository()
    async with CelerySessionLocal() as db:
        _log_task_start("embeddings.rebuild_document", task_id, document_id, db)
        document = await documents.get_by_id(db, document_id)

        if document is None:
            return

        if document.embedding_status != EmbeddingStatus.QUEUED:
            return

        project = await ProjectRepository().get_by_id(db, document.project_id)
        embedding_service = await resolve_embedding_service(
            db, project.user_id if project else None
        )

        document.embedding_status = EmbeddingStatus.PROCESSING
        await db.commit()

        service = EmbeddingManagementService(embedding_service=embedding_service)

        try:
            await service.rebuild_document_embeddings(
                db=db,
                document_id=document_id,
                force=force,
                should_cancel=lambda: _document_embedding_cancelled(document_id),
            )
            await db.refresh(document)
            if document.embedding_status in (
                EmbeddingStatus.CANCELLING,
                EmbeddingStatus.CANCELLED,
            ):
                document.embedding_status = EmbeddingStatus.CANCELLED
                document.celery_task_id = None
                await db.commit()
                return
            await documents.mark_embeddings_current(
                db,
                document,
                provider=service.embedding_service.provider,
                model_name=service.embedding_service.model_name,
                dimensions=service.embedding_service.dimensions,
                updated_at=datetime.now(timezone.utc),
            )
        except EmbeddingExecutionCancelled:
            await db.rollback()
            async with CelerySessionLocal() as recovery_db:
                recovery_document = await documents.get_by_id(recovery_db, document_id)
                if recovery_document is not None:
                    recovery_document.embedding_status = EmbeddingStatus.CANCELLED
                    recovery_document.celery_task_id = None
                    await recovery_db.commit()
        except Exception as exc:
            await db.rollback()
            async with CelerySessionLocal() as recovery_db:
                recovery_document = await documents.get_by_id(recovery_db, document_id)
                if (
                    recovery_document is not None
                    and recovery_document.embedding_status
                    not in (EmbeddingStatus.CANCELLING, EmbeddingStatus.CANCELLED)
                ):
                    recovery_document.embedding_status = EmbeddingStatus.FAILED
                    recovery_document.celery_task_id = None
                    recovery_document.processing_error = str(exc)
                    await recovery_db.commit()
            raise


async def _sync_project_embeddings(
    project_id: int,
    task_id: str | None = None,
    documents: DocumentRepository | None = None,
    projects: ProjectRepository | None = None,
) -> None:
    documents = documents or DocumentRepository()
    projects = projects or ProjectRepository()
    async with CelerySessionLocal() as db:
        _log_task_start("embeddings.sync_project", task_id, project_id, db)
        project = await projects.get_by_id(db, project_id)

        if project is None:
            return

        if project.embedding_sync_status != EmbeddingStatus.QUEUED:
            return

        embedding_service = await resolve_embedding_service(db, project.user_id)

        project.embedding_sync_status = EmbeddingStatus.PROCESSING
        await db.commit()

        service = EmbeddingManagementService(embedding_service=embedding_service)

        try:
            await service.sync_project_embeddings(
                db=db,
                project_id=project_id,
                should_cancel=lambda: _project_embedding_cancelled(project_id),
            )
            await db.refresh(project)
            if project.embedding_sync_status in (
                EmbeddingStatus.CANCELLING,
                EmbeddingStatus.CANCELLED,
            ):
                project.embedding_sync_status = EmbeddingStatus.CANCELLED
                project.embedding_sync_task_id = None
                await db.commit()
                return
            await documents.mark_project_embeddings_current(
                db,
                project_id=project_id,
                provider=service.embedding_service.provider,
                model_name=service.embedding_service.model_name,
                dimensions=service.embedding_service.dimensions,
                updated_at=datetime.now(timezone.utc),
            )
            project.embedding_sync_status = EmbeddingStatus.COMPLETED
            project.embedding_sync_task_id = None
            project.embedding_sync_error = None
            await db.commit()
        except EmbeddingExecutionCancelled:
            await db.rollback()
            async with CelerySessionLocal() as recovery_db:
                recovery_project = await projects.get_by_id(recovery_db, project_id)
                if recovery_project is not None:
                    recovery_project.embedding_sync_status = EmbeddingStatus.CANCELLED
                    recovery_project.embedding_sync_task_id = None
                    await recovery_db.commit()
        except Exception as exc:
            await db.rollback()
            async with CelerySessionLocal() as recovery_db:
                recovery_project = await projects.get_by_id(recovery_db, project_id)
                if (
                    recovery_project is not None
                    and recovery_project.embedding_sync_status
                    not in (EmbeddingStatus.CANCELLING, EmbeddingStatus.CANCELLED)
                ):
                    recovery_project.embedding_sync_status = EmbeddingStatus.FAILED
                    recovery_project.embedding_sync_task_id = None
                    recovery_project.embedding_sync_error = str(exc)
                    await recovery_db.commit()
            raise


@celery_app.task(name="embeddings.rebuild_document", bind=True)
def rebuild_document_embeddings_task(self, document_id: int, force: bool = True) -> None:
    asyncio.run(_rebuild_document_embeddings(document_id, self.request.id, force))


@celery_app.task(name="embeddings.sync_project", bind=True)
def sync_project_embeddings_task(self, project_id: int) -> None:
    asyncio.run(_sync_project_embeddings(project_id, self.request.id))
