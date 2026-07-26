from math import ceil

from fastapi import APIRouter, Query, status

from app.dependencies import (
    BackgroundJobServiceDep,
    CurrentUserDep,
    DbSessionDep,
    OwnedWorkflowRunDep,
    WorkflowEventRepositoryDep,
    WorkflowRunRepositoryDep,
    WorkflowServiceDep,
)
from app.enums import WorkflowRunStatus
from app.schemas import (
    WorkflowEventResponse,
    WorkflowRunBulkDeleteResponse,
    WorkflowRunListResponse,
    WorkflowRunResponse,
)

router = APIRouter()

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
DEFAULT_STATUS_FILTER = None
DEFAULT_PROJECT_ID = None
DEFAULT_STATUS_QUERY = Query(DEFAULT_STATUS_FILTER, alias="status")


# -------------------------------------------------
#  LIST WORKFLOW RUNS
# -------------------------------------------------
@router.get(
    "/runs",
    response_model=WorkflowRunListResponse,
)
async def list_workflow_runs(
    db: DbSessionDep,
    user: CurrentUserDep,
    runs: WorkflowRunRepositoryDep,
    page: int = Query(DEFAULT_PAGE, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=100),
    status_filter: WorkflowRunStatus | None = DEFAULT_STATUS_QUERY,
    project_id: int | None = Query(DEFAULT_PROJECT_ID, ge=1),
):
    total = await runs.count_for_user(
        db=db,
        user_id=user.id,
        status=status_filter,
        project_id=project_id,
    )
    items = await runs.list_for_user(
        db=db,
        user_id=user.id,
        status=status_filter,
        project_id=project_id,
        limit=page_size,
        offset=(page - 1) * page_size,
    )

    return WorkflowRunListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total else 0,
    )

# -------------------------------------------------
#  GET SINGLE WORKFLOW RUN
# -------------------------------------------------
@router.get(
    "/runs/{run_id}",
    response_model=WorkflowRunResponse,
)
async def get_workflow_run(
    workflow_run: OwnedWorkflowRunDep,
):
    return workflow_run


# -------------------------------------------------
#  RESUME WORKFLOW RUN
# -------------------------------------------------
@router.post(
    ("/runs/{run_id}/resume"),
    response_model=WorkflowRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_workflow(
    db: DbSessionDep,
    workflow_run: OwnedWorkflowRunDep,
    service: WorkflowServiceDep,
    jobs: BackgroundJobServiceDep,
):
    workflow_run = await service.enqueue_resume(db, workflow_run, jobs)

    return service.run_response(workflow_run)


# -------------------------------------------------
#  RETRY WORKFLOW RUN
# -------------------------------------------------
@router.post(
    "/runs/{run_id}/retry",
    response_model=WorkflowRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_workflow(
    db: DbSessionDep,
    workflow_run: OwnedWorkflowRunDep,
    service: WorkflowServiceDep,
    jobs: BackgroundJobServiceDep,
):
    workflow_run = await service.enqueue_retry(db, workflow_run, jobs)

    return service.run_response(workflow_run)

# -------------------------------------------------
#  CANCEL WORKFLOW RUN
# -------------------------------------------------
@router.post(
    "/runs/{run_id}/cancel",
    response_model=WorkflowRunResponse,
)
async def cancel_workflow_run(
    db: DbSessionDep,
    workflow_run: OwnedWorkflowRunDep,
    service: WorkflowServiceDep,
    jobs: BackgroundJobServiceDep,
):
    workflow_run = await service.cancel_run(db, workflow_run, jobs)
    return service.run_response(workflow_run)

# -------------------------------------------------
#  DELETE CANCELED WORKFLOW RUNS
# -------------------------------------------------
@router.delete(
    "/runs/canceled",
    response_model=WorkflowRunBulkDeleteResponse,
)
async def delete_canceled_workflow_runs(
    db: DbSessionDep,
    user: CurrentUserDep,
    service: WorkflowServiceDep,
    project_id: int | None = Query(None, ge=1),
):
    deleted = await service.delete_canceled_runs(
        db=db,
        user_id=user.id,
        project_id=project_id,
    )
    return WorkflowRunBulkDeleteResponse(deleted=deleted)

# -------------------------------------------------
#  DELETE WORKFLOW RUN
# -------------------------------------------------
@router.delete(
    "/runs/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_workflow_run(
    db: DbSessionDep,
    workflow_run: OwnedWorkflowRunDep,
    service: WorkflowServiceDep,
):
    await service.delete_run(db, workflow_run)


# add later:

# GET /workflow_runs

# with filters:

# GET /workflow_runs?workflow_id=1
# GET /workflow_runs?status=completed
# GET /workflow_runs?status=failed

# This becomes very useful once you have dozens of runs.

# A workflow engine almost always needs a "list runs" endpoint.


# -------------------------------------------------
#  GET WORKFLOW EVENTS
# -------------------------------------------------
@router.get(
    "/runs/{run_id}/events",
    response_model=list[WorkflowEventResponse],
)
async def get_workflow_events(
    db: DbSessionDep,
    workflow_run: OwnedWorkflowRunDep,
    events: WorkflowEventRepositoryDep,
):

    return await events.get_for_run(
        db=db,
        run_id=workflow_run.id,
    )


# 10,000+ events
# will become expensive.

# Future:
# GET /workflow_runs/{run_id}/events?limit=100&offset=0
