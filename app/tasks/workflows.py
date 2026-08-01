import asyncio
import logging
import os

from app.core.celery_app import celery_app
from app.core.celery_database import CelerySessionLocal, safe_database_url
from app.enums import WorkflowRunStatus
from app.repositories import WorkflowRunRepository
from app.services.workflow import DAGEngine, EventBus
from app.services.workflow.workflow import WorkflowService
from app.tasks.provider_config import load_provider_config

logger = logging.getLogger(__name__)


def _build_service() -> WorkflowService:
    return WorkflowService(
        runs=WorkflowRunRepository(),
        events=EventBus(),
        engine=DAGEngine(),
    )


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


async def _run_workflow(run_id: int, task_id: str | None = None) -> None:
    async with CelerySessionLocal() as db:
        _log_task_start("workflows.run", task_id, run_id, db)
        await load_provider_config(db)
        runs = WorkflowRunRepository()
        workflow_run = await runs.claim_pending(db, run_id)

        if workflow_run is None:
            return

        service = _build_service()
        try:
            await service.execute_run(db, workflow_run)
        except Exception:
            # WorkflowService.execute_run() already marks the run FAILED
            # and commits that in its own except block
            # (app/services/workflow/workflow.py) before re-raising here.
            # Repeating that in a second, freshly opened session was
            # redundant (see the equivalent documents.py fix -- the same
            # pattern there crashed with a SQLAlchemy MissingGreenlet
            # error reading an expired attribute right after rollback).
            # Just roll back this session and propagate for Celery's own
            # logging/retry visibility.
            await db.rollback()
            raise


async def _resume_workflow(run_id: int, task_id: str | None = None) -> None:
    async with CelerySessionLocal() as db:
        _log_task_start("workflows.resume", task_id, run_id, db)
        await load_provider_config(db)
        runs = WorkflowRunRepository()
        workflow_run = await runs.get_by_id(db, run_id)

        if workflow_run is None:
            return

        if workflow_run.status != WorkflowRunStatus.RUNNING:
            # The endpoint claims the run (-> RUNNING) before enqueuing, so
            # anything else here means it was already picked up/finished.
            return

        service = _build_service()
        try:
            await service.resume_run(db, workflow_run)
        except Exception:
            # See the matching comment in _run_workflow() above --
            # WorkflowService.resume_run() already marks the run FAILED
            # before re-raising, so the second fail-handling pass here was
            # redundant.
            await db.rollback()
            raise


@celery_app.task(name="workflows.run", bind=True)
def run_workflow_task(self, run_id: int) -> None:
    asyncio.run(_run_workflow(run_id, self.request.id))


@celery_app.task(name="workflows.resume", bind=True)
def resume_workflow_task(self, run_id: int) -> None:
    asyncio.run(_resume_workflow(run_id, self.request.id))
