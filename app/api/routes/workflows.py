
from fastapi import APIRouter, Request, status
from starlette.responses import StreamingResponse

from app.dependencies import (
    BackgroundJobServiceDep,
    DbSessionDep,
    OwnedProjectDep,
    OwnedWorkflowDep,
    WorkflowRepositoryDep,
    WorkflowServiceDep,
    WorkflowUpdateServiceDep,
)
from app.schemas import (
    WorkflowCreate,
    WorkflowResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowUpdate,
)

router = APIRouter()


# -------------------------------------------------
# CREATE WORKFLOW
# -------------------------------------------------
@router.post(
    "/projects/{project_id}/workflows",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow(
    payload: WorkflowCreate,
    db: DbSessionDep,
    project: OwnedProjectDep,
    service: WorkflowUpdateServiceDep,
):
    return await service.create(db=db, payload=payload, project=project)


# -------------------------------------------------
# GET SINGLE WORKFLOW
# -------------------------------------------------
@router.get(
    "/workflows/{workflow_id}",
    response_model=WorkflowResponse,
)
async def get_workflow(
    workflow: OwnedWorkflowDep,
):
    return workflow


# -------------------------------------------------
# UPDATE WORKFLOW
# -------------------------------------------------
@router.patch(
    "/workflows/{workflow_id}",
    response_model=WorkflowResponse,
)
async def update_workflow(
    payload: WorkflowUpdate,
    db: DbSessionDep,
    workflow: OwnedWorkflowDep,
    service: WorkflowUpdateServiceDep,
):
    return await service.update(
        db=db,
        workflow=workflow,
        payload=payload,
    )


# -------------------------------------------------
# GET WORKFLOWS
# -------------------------------------------------
@router.get(
    "/projects/{project_id}/workflows",
    response_model=list[WorkflowResponse],
)
async def get_workflows(
    db: DbSessionDep,
    project: OwnedProjectDep,
    workflows: WorkflowRepositoryDep,
):
    return await workflows.list_for_project(
        db,
        project.id,
    )


# -------------------------------------------------
# DELETE WORKFLOW
# -------------------------------------------------
@router.delete(
    "/workflows/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_workflow(
    db: DbSessionDep,
    workflow: OwnedWorkflowDep,
    service: WorkflowUpdateServiceDep,
):
    await service.delete(db, workflow)


# -------------------------------------------------
#  CREATE WORKFLOW RUN
# -------------------------------------------------
@router.post(
    "/workflows/{workflow_id}/run",
    response_model=WorkflowRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_workflow(
    payload: WorkflowRunRequest,
    db: DbSessionDep,
    service: WorkflowServiceDep,
    workflow: OwnedWorkflowDep,
    jobs: BackgroundJobServiceDep,
):
    workflow_run = await service.enqueue_run(
        db=db,
        workflow_id=workflow.id,
        user_input=payload.input,
        jobs=jobs,
    )

    return service.run_response(workflow_run)


# -------------------------------------------------
# STREAMING ROUTE
# -------------------------------------------------
@router.post("/workflows/{workflow_id}/runs/stream")
async def run_workflow_stream(
    request: Request,
    payload: WorkflowRunRequest,
    db: DbSessionDep,
    workflow: OwnedWorkflowDep,
    service: WorkflowServiceDep,
):
    return StreamingResponse(
        service.run_workflow_stream_until_disconnected(
            db=db,
            workflow_id=workflow.id,
            user_input=payload.input,
            is_disconnected=request.is_disconnected,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
