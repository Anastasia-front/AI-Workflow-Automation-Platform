import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from app.core import STALE_AFTER, AsyncSessionLocal
from app.enums import WorkflowRunStatus
from app.repositories import WorkflowRunRepository
from app.services.background_jobs import BackgroundJobService

logger = logging.getLogger(__name__)


async def recover_running_workflows(
    jobs: BackgroundJobService | None = None,
) -> None:
    """Run once at API startup. Re-enqueues only runs that are actually
    stale (no progress for STALE_AFTER) -- a run that is genuinely still
    being processed by a live worker is left alone, since blindly
    re-enqueuing every PENDING/RUNNING record would double-execute work
    that Celery is already doing.

    This replaces the previous fire-and-forget `asyncio.create_task`
    in-process recovery, which was not durable and did not survive an API
    process restart itself.
    """
    from app.tasks.workflows import resume_workflow_task, run_workflow_task

    jobs = jobs or BackgroundJobService()
    cutoff = datetime.now(timezone.utc) - STALE_AFTER

    async with AsyncSessionLocal() as db:
        runs_repo = WorkflowRunRepository()
        stale_runs = await runs_repo.get_stale(db, older_than=cutoff)

    for run in stale_runs:
        try:
            if run.status == WorkflowRunStatus.PENDING:
                # Never actually started -- safe to hand back to the queue,
                # the task's own claim guard prevents double execution.
                jobs.enqueue(run_workflow_task, run.id)
            elif run.status == WorkflowRunStatus.RUNNING:
                # Started but the worker died before completing. Re-enqueue
                # as a resume so the DAG engine can pick up completed steps.
                jobs.enqueue(resume_workflow_task, run.id)
        except HTTPException as exc:
            logger.warning(
                "Skipping workflow recovery enqueue for run %s: %s",
                run.id,
                exc.detail,
            )
