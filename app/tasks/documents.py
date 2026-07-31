import asyncio
import logging
import os

from app.core.celery_app import celery_app
from app.core.celery_database import CelerySessionLocal, safe_database_url
from app.enums import DocumentStatus
from app.repositories import DocumentRepository
from app.services import DocumentService
from app.tasks.provider_config import load_provider_config

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


async def _process_document(document_id: int, task_id: str | None = None) -> None:
    async with CelerySessionLocal() as db:
        _log_task_start("documents.process", task_id, document_id, db)
        await load_provider_config(db)
        documents = DocumentRepository()
        document = await documents.get_by_id(db, document_id)

        if document is None:
            return

        # Idempotency / duplicate-submission guard: only a document that is
        # still QUEUED (i.e. not already picked up by another worker or
        # already finished) may be claimed by this task run.
        if document.status != DocumentStatus.QUEUED:
            return

        service = DocumentService(documents=documents)

        try:
            await service.process(db, document)
        except Exception:
            # DocumentService.process() already marks the document FAILED
            # and commits that in its own except block (app/services/document.py)
            # before re-raising here. Repeating that in a second, freshly
            # opened session was redundant and could itself raise a
            # SQLAlchemy MissingGreenlet error, which left the document
            # stuck (e.g. at "processing") instead of ending at FAILED.
            # Just roll back this session and propagate for Celery's own
            # logging/retry visibility.
            await db.rollback()
            raise


@celery_app.task(name="documents.process", bind=True)
def process_document_task(self, document_id: int) -> None:
    asyncio.run(_process_document(document_id, self.request.id))
