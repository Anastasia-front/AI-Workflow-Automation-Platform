"""Tests for the Celery-backed persistent background job pipeline.

These tests avoid a real Postgres/Redis dependency: DB access is mocked at
the repository/session boundary, and Celery `.delay()` calls are patched so
no broker is required. They exercise the logic that matters for this
feature -- claim guards (idempotency / duplicate submission), status
transitions, and recovery routing -- not the ORM/DB wiring itself.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.enums import DocumentStatus, EmbeddingStatus, WorkflowRunStatus


def _fake_session_ctx(fake_db):
    @asynccontextmanager
    async def _ctx():
        yield fake_db

    return _ctx


def test_celery_database_uses_nullpool_and_separate_factory():
    from sqlalchemy.pool import NullPool

    from app.core import celery_database, database

    celery_database.reset_celery_database()
    engine = celery_database.get_celery_engine()

    assert engine is not database.engine
    assert isinstance(engine.sync_engine.pool, NullPool)

    celery_database.reset_celery_database()


@pytest.mark.asyncio
async def test_each_celery_task_uses_own_session():
    from app.tasks import workflows as tasks_workflows

    first_db = AsyncMock()
    second_db = AsyncMock()
    sessions = [first_db, second_db]

    @asynccontextmanager
    async def session_ctx():
        yield sessions.pop(0)

    with patch.object(tasks_workflows, "CelerySessionLocal", session_ctx), \
         patch.object(tasks_workflows, "WorkflowRunRepository") as repo_cls, \
         patch.object(tasks_workflows, "_run_owner_user_id", AsyncMock(return_value=None)), \
         patch.object(tasks_workflows, "resolve_ai_service", AsyncMock(return_value=MagicMock())), \
         patch.object(tasks_workflows, "_build_service") as build_service:
        repo_cls.return_value.claim_pending = AsyncMock(
            side_effect=[
                MagicMock(status=WorkflowRunStatus.RUNNING),
                MagicMock(status=WorkflowRunStatus.RUNNING),
            ]
        )
        build_service.return_value.execute_run = AsyncMock()

        await tasks_workflows._run_workflow(run_id=1)
        await tasks_workflows._run_workflow(run_id=2)

        calls = build_service.return_value.execute_run.await_args_list
        assert calls[0].args[0] is first_db
        assert calls[1].args[0] is second_db


@pytest.mark.asyncio
async def test_workflow_failure_rolls_back_and_persists_with_recovery_session():
    from app.tasks import workflows as tasks_workflows

    run = MagicMock(status=WorkflowRunStatus.RUNNING)
    recovery_run = MagicMock(status=WorkflowRunStatus.RUNNING)
    main_db = AsyncMock()
    recovery_db = AsyncMock()
    sessions = [main_db, recovery_db]

    @asynccontextmanager
    async def session_ctx():
        yield sessions.pop(0)

    with patch.object(tasks_workflows, "CelerySessionLocal", session_ctx), \
         patch.object(tasks_workflows, "WorkflowRunRepository") as repo_cls, \
         patch.object(tasks_workflows, "_run_owner_user_id", AsyncMock(return_value=None)), \
         patch.object(tasks_workflows, "resolve_ai_service", AsyncMock(return_value=MagicMock())), \
         patch.object(tasks_workflows, "_build_service") as build_service:
        repo = repo_cls.return_value
        repo.claim_pending = AsyncMock(return_value=run)
        repo.get_by_id = AsyncMock(return_value=recovery_run)
        repo.fail_with_error = AsyncMock(return_value=recovery_run)
        build_service.return_value.execute_run = AsyncMock(
            side_effect=RuntimeError("boom")
        )

        with pytest.raises(RuntimeError):
            await tasks_workflows._run_workflow(run_id=1)

        main_db.rollback.assert_awaited_once()
        repo.fail_with_error.assert_awaited_once_with(
            recovery_db,
            recovery_run,
            "boom",
        )


# ---------------------------------------------------------------------------
# Document processing task
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_document_task_skips_when_not_queued():
    """Duplicate-submission / idempotency guard: a task fired for a document
    that is no longer QUEUED (already processed, or claimed by another
    worker) must be a no-op, never re-running extraction/embedding."""
    from app.tasks import documents as tasks_documents

    document = MagicMock(status=DocumentStatus.PROCESSING)
    fake_db = AsyncMock()

    with patch.object(tasks_documents, "CelerySessionLocal", _fake_session_ctx(fake_db)), \
         patch.object(tasks_documents, "DocumentRepository") as repo_cls, \
         patch.object(tasks_documents, "DocumentService") as service_cls:
        repo_cls.return_value.get_by_id = AsyncMock(return_value=document)

        await tasks_documents._process_document(document_id=1)

        service_cls.return_value.process.assert_not_called()


@pytest.mark.asyncio
async def test_process_document_task_runs_when_queued():
    from app.tasks import documents as tasks_documents

    document = MagicMock(status=DocumentStatus.QUEUED)
    fake_db = AsyncMock()

    with patch.object(tasks_documents, "CelerySessionLocal", _fake_session_ctx(fake_db)), \
         patch.object(tasks_documents, "DocumentRepository") as repo_cls, \
         patch.object(tasks_documents, "ProjectRepository") as project_repo_cls, \
         patch.object(tasks_documents, "resolve_embedding_service", AsyncMock(return_value=MagicMock())), \
         patch.object(tasks_documents, "DocumentService") as service_cls:
        repo_cls.return_value.get_by_id = AsyncMock(return_value=document)
        project_repo_cls.return_value.get_by_id = AsyncMock(return_value=None)
        service_cls.return_value.process = AsyncMock(return_value=document)

        await tasks_documents._process_document(document_id=1)

        service_cls.return_value.process.assert_awaited_once_with(fake_db, document)


@pytest.mark.asyncio
async def test_process_document_task_records_error_on_failure():
    from app.tasks import documents as tasks_documents

    document = MagicMock(status=DocumentStatus.QUEUED, processing_error=None)
    fake_db = AsyncMock()

    with patch.object(tasks_documents, "CelerySessionLocal", _fake_session_ctx(fake_db)), \
         patch.object(tasks_documents, "DocumentRepository") as repo_cls, \
         patch.object(tasks_documents, "ProjectRepository") as project_repo_cls, \
         patch.object(tasks_documents, "resolve_embedding_service", AsyncMock(return_value=MagicMock())), \
         patch.object(tasks_documents, "DocumentService") as service_cls:
        repo_cls.return_value.get_by_id = AsyncMock(return_value=document)
        project_repo_cls.return_value.get_by_id = AsyncMock(return_value=None)
        repo_cls.return_value.fail_processing = AsyncMock(return_value=document)
        service_cls.return_value.process = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError):
            await tasks_documents._process_document(document_id=1)

        service_cls.return_value.process.assert_awaited_once_with(fake_db, document)


# ---------------------------------------------------------------------------
# Workflow run / resume tasks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_workflow_task_skips_when_not_pending():
    """Guards against two workers (or a duplicate resubmission) executing
    the same workflow run concurrently."""
    from app.tasks import workflows as tasks_workflows

    run = MagicMock(status=WorkflowRunStatus.RUNNING)
    fake_db = AsyncMock()

    with patch.object(tasks_workflows, "CelerySessionLocal", _fake_session_ctx(fake_db)), \
         patch.object(tasks_workflows, "WorkflowRunRepository") as repo_cls, \
         patch.object(tasks_workflows, "_build_service") as build_service:
        repo_cls.return_value.claim_pending = AsyncMock(return_value=None)
        service = MagicMock()
        service.execute_run = AsyncMock()
        build_service.return_value = service

        await tasks_workflows._run_workflow(run_id=1)

        service.execute_run.assert_not_called()


@pytest.mark.asyncio
async def test_run_workflow_task_executes_when_pending():
    from app.tasks import workflows as tasks_workflows

    run = MagicMock(status=WorkflowRunStatus.PENDING)
    fake_db = AsyncMock()

    with patch.object(tasks_workflows, "CelerySessionLocal", _fake_session_ctx(fake_db)), \
         patch.object(tasks_workflows, "WorkflowRunRepository") as repo_cls, \
         patch.object(tasks_workflows, "_run_owner_user_id", AsyncMock(return_value=None)), \
         patch.object(tasks_workflows, "resolve_ai_service", AsyncMock(return_value=MagicMock())), \
         patch.object(tasks_workflows, "_build_service") as build_service:
        repo_cls.return_value.claim_pending = AsyncMock(return_value=run)
        service = MagicMock()
        service.execute_run = AsyncMock()
        build_service.return_value = service

        await tasks_workflows._run_workflow(run_id=1)

        service.execute_run.assert_awaited_once_with(fake_db, run)


@pytest.mark.asyncio
async def test_resume_workflow_task_skips_when_not_running():
    from app.tasks import workflows as tasks_workflows

    run = MagicMock(status=WorkflowRunStatus.FAILED)
    fake_db = AsyncMock()

    with patch.object(tasks_workflows, "CelerySessionLocal", _fake_session_ctx(fake_db)), \
         patch.object(tasks_workflows, "WorkflowRunRepository") as repo_cls, \
         patch.object(tasks_workflows, "_build_service") as build_service:
        repo_cls.return_value.get_by_id = AsyncMock(return_value=run)
        service = MagicMock()
        service.resume_run = AsyncMock()
        build_service.return_value = service

        await tasks_workflows._resume_workflow(run_id=1)

        service.resume_run.assert_not_called()


# ---------------------------------------------------------------------------
# Worker-restart / stale-job recovery
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recovery_only_reenqueues_stale_runs():
    """recover_running_workflows must not blindly re-enqueue every
    PENDING/RUNNING record -- only ones the repository considers stale
    (no progress for STALE_AFTER) -- and must route PENDING vs RUNNING to
    the correct task."""
    from app.services.workflow import recovery

    pending_run = MagicMock(id=1, status=WorkflowRunStatus.PENDING)
    running_run = MagicMock(id=2, status=WorkflowRunStatus.RUNNING)

    fake_db = AsyncMock()

    with patch.object(recovery, "AsyncSessionLocal", _fake_session_ctx(fake_db)), \
         patch.object(recovery, "WorkflowRunRepository") as repo_cls, \
         patch("app.tasks.workflows.run_workflow_task") as run_task, \
         patch("app.tasks.workflows.resume_workflow_task") as resume_task:
        repo_cls.return_value.get_stale = AsyncMock(
            return_value=[pending_run, running_run]
        )

        jobs = MagicMock()

        await recovery.recover_running_workflows(jobs=jobs)

        jobs.enqueue.assert_any_call(run_task, 1)
        jobs.enqueue.assert_any_call(resume_task, 2)


@pytest.mark.asyncio
async def test_recovery_passes_stale_cutoff():
    from app.services.workflow import recovery

    fake_db = AsyncMock()

    with patch.object(recovery, "AsyncSessionLocal", _fake_session_ctx(fake_db)), \
         patch.object(recovery, "WorkflowRunRepository") as repo_cls:
        repo_cls.return_value.get_stale = AsyncMock(return_value=[])

        before = datetime.now(timezone.utc) - recovery.STALE_AFTER
        await recovery.recover_running_workflows()
        after = datetime.now(timezone.utc) - recovery.STALE_AFTER

        _, kwargs = repo_cls.return_value.get_stale.call_args
        cutoff = kwargs["older_than"]
        assert before - timedelta(seconds=5) <= cutoff <= after + timedelta(seconds=5)


@pytest.mark.asyncio
async def test_recovery_skips_enqueue_errors_without_crashing():
    from app.services.workflow import recovery

    pending_run = MagicMock(id=1, status=WorkflowRunStatus.PENDING)
    fake_db = AsyncMock()
    jobs = MagicMock()
    jobs.enqueue.side_effect = HTTPException(status_code=503, detail="queue down")

    with patch.object(recovery, "AsyncSessionLocal", _fake_session_ctx(fake_db)), \
         patch.object(recovery, "WorkflowRunRepository") as repo_cls:
        repo_cls.return_value.get_stale = AsyncMock(return_value=[pending_run])

        await recovery.recover_running_workflows(jobs=jobs)

        jobs.enqueue.assert_called_once()


# ---------------------------------------------------------------------------
# API-level duplicate-submission guards
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_document_endpoint_skips_enqueue_when_already_queued():
    from app.api.routes import documents as documents_route

    document = MagicMock(
        id=1,
        status=DocumentStatus.QUEUED,
        celery_task_id="existing-task-id",
        processing_started_at=None,
        processing_finished_at=None,
        processing_duration_ms=None,
        processing_error=None,
        embedding_status=EmbeddingStatus.PENDING,
    )
    fake_db = AsyncMock()
    chunks_repo = AsyncMock()
    chunks_repo.count_for_document = AsyncMock(return_value=0)
    service = AsyncMock()
    service.enqueue_processing = AsyncMock(return_value=document)
    jobs = MagicMock()

    response = await documents_route.process_document(
        db=fake_db,
        document=document,
        chunks=chunks_repo,
        service=service,
        jobs=jobs,
    )

    service.enqueue_processing.assert_awaited_once_with(fake_db, document, jobs)
    assert response.celery_task_id == "existing-task-id"
    assert response.status == DocumentStatus.QUEUED


@pytest.mark.asyncio
async def test_document_service_enqueues_when_uploaded():
    from app.services import DocumentService
    from app.tasks.documents import process_document_task

    document = MagicMock(
        id=1,
        status=DocumentStatus.UPLOADED,
        celery_task_id=None,
        processing_started_at=None,
        processing_finished_at=None,
        processing_duration_ms=None,
        processing_error=None,
        embedding_status=EmbeddingStatus.PENDING,
    )
    fake_db = AsyncMock()
    jobs = MagicMock()
    jobs.enqueue.return_value = MagicMock(id="new-task-id")

    result = await DocumentService().enqueue_processing(fake_db, document, jobs)

    jobs.enqueue.assert_called_once_with(process_document_task, 1)
    assert result is document
    assert document.status == DocumentStatus.QUEUED
    assert document.celery_task_id == "new-task-id"


@pytest.mark.asyncio
async def test_document_service_restores_status_when_queue_unavailable():
    from app.services import DocumentService

    document = MagicMock(
        id=1,
        status=DocumentStatus.UPLOADED,
        celery_task_id=None,
        processing_started_at=None,
        processing_finished_at=None,
        processing_duration_ms=None,
        processing_error=None,
        embedding_status=EmbeddingStatus.PENDING,
    )
    fake_db = AsyncMock()
    jobs = MagicMock()
    jobs.enqueue.side_effect = HTTPException(status_code=503, detail="queue down")

    with pytest.raises(HTTPException) as exc_info:
        await DocumentService().enqueue_processing(fake_db, document, jobs)

    assert exc_info.value.status_code == 503
    assert document.status == DocumentStatus.UPLOADED


@pytest.mark.asyncio
async def test_resume_workflow_endpoint_rejects_non_resumable_status():
    from app.services import WorkflowService

    run = MagicMock(status=WorkflowRunStatus.RUNNING)
    service = WorkflowService(
        runs=MagicMock(),
        events=MagicMock(),
        engine=MagicMock(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.enqueue_resume(AsyncMock(), run, MagicMock())

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_resume_workflow_endpoint_claims_and_enqueues_when_failed():
    from app.services import WorkflowService
    from app.tasks.workflows import resume_workflow_task

    run = MagicMock(id=1, status=WorkflowRunStatus.FAILED)
    fake_db = AsyncMock()
    jobs = MagicMock()
    jobs.enqueue.return_value = MagicMock(id="resume-task-id")
    runs = MagicMock()
    runs.start = AsyncMock(side_effect=lambda db, run: _set_run_status(run, WorkflowRunStatus.RUNNING))
    runs.set_task_id = AsyncMock(side_effect=lambda db, run, task_id: _set_run_task(run, task_id))
    service = WorkflowService(
        runs=runs,
        events=MagicMock(),
        engine=MagicMock(),
    )

    result = await service.enqueue_resume(fake_db, run, jobs)

    assert result is run
    assert run.status == WorkflowRunStatus.RUNNING
    assert run.celery_task_id == "resume-task-id"
    jobs.enqueue.assert_called_once_with(resume_workflow_task, run.id)


@pytest.mark.asyncio
async def test_resume_workflow_endpoint_restores_status_when_queue_unavailable():
    from app.services import WorkflowService

    run = MagicMock(id=1, status=WorkflowRunStatus.FAILED)
    fake_db = AsyncMock()
    jobs = MagicMock()
    jobs.enqueue.side_effect = HTTPException(status_code=503, detail="queue down")
    runs = MagicMock()
    runs.start = AsyncMock(side_effect=lambda db, run: _set_run_status(run, WorkflowRunStatus.RUNNING))
    runs.set_status = AsyncMock(side_effect=lambda db, run, status: _set_run_status(run, status))
    service = WorkflowService(
        runs=runs,
        events=MagicMock(),
        engine=MagicMock(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.enqueue_resume(fake_db, run, jobs)

    assert exc_info.value.status_code == 503
    assert run.status == WorkflowRunStatus.FAILED


@pytest.mark.asyncio
async def test_workflow_service_marks_run_failed_when_queue_unavailable():
    from app.services import WorkflowService

    run = MagicMock(
        id=1,
        status=WorkflowRunStatus.PENDING,
        error=None,
        celery_task_id=None,
    )
    fake_db = AsyncMock()
    runs = MagicMock()
    runs.create_committed = AsyncMock(return_value=run)
    runs.fail_with_error = AsyncMock(side_effect=lambda db, run, error: _fail_run(run, error))
    jobs = MagicMock()
    jobs.enqueue.side_effect = HTTPException(status_code=503, detail="queue down")
    service = WorkflowService(
        runs=runs,
        events=MagicMock(),
        engine=MagicMock(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.enqueue_run(
            db=fake_db,
            workflow_id=10,
            user_input="hello",
            jobs=jobs,
        )

    assert exc_info.value.status_code == 503
    assert run.status == WorkflowRunStatus.FAILED
    assert run.error == "Background job queue is unavailable."


@pytest.mark.asyncio
async def test_workflow_service_cancels_running_run_and_revokes_task():
    from app.services import WorkflowService

    run = MagicMock(
        id=1,
        status=WorkflowRunStatus.RUNNING,
        celery_task_id="task-id",
    )
    fake_db = AsyncMock()
    jobs = MagicMock()
    runs = MagicMock()
    runs.cancel = AsyncMock(side_effect=lambda db, run: _set_run_status(run, WorkflowRunStatus.CANCELED))
    service = WorkflowService(
        runs=runs,
        events=MagicMock(),
        engine=MagicMock(),
    )

    result = await service.cancel_run(fake_db, run, jobs)

    assert result is run
    assert run.status == WorkflowRunStatus.CANCELED
    jobs.revoke.assert_called_once_with("task-id", terminate=True)


def _set_run_status(run, status):
    run.status = status
    return run


def _set_run_task(run, task_id):
    run.celery_task_id = task_id
    return run


def _fail_run(run, error):
    run.status = WorkflowRunStatus.FAILED
    run.error = error
    return run
