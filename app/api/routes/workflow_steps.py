
from fastapi import APIRouter, status

from app.dependencies import (
    DbSessionDep,
    OwnedWorkflowDep,
    OwnedWorkflowStepDep,
    WorkflowStepRepositoryDep,
    WorkflowStepUpdateServiceDep,
)
from app.schemas import WorkflowStepCreate, WorkflowStepResponse

router = APIRouter()

# -------------------------------------------------
# CREATE WORKFLOW STEP
# -------------------------------------------------
@router.post(
    "/workflows/{workflow_id}/steps",
    response_model=WorkflowStepResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow_step(
    payload: WorkflowStepCreate,
    db: DbSessionDep,
    workflow: OwnedWorkflowDep,
    service: WorkflowStepUpdateServiceDep,
):
    return await service.create(
        db=db,
        payload=payload,
        workflow=workflow,
    )

# -------------------------------------------------
#  GET SINGLE WORKFLOW STEP
# -------------------------------------------------
@router.get(
    "/steps/{step_id}", 
    response_model=WorkflowStepResponse
)
async def get_step(
    step: OwnedWorkflowStepDep,
):
    return step

# -------------------------------------------------
# GET WORKFLOW STEPS
# -------------------------------------------------
@router.get(
    "/workflows/{workflow_id}/steps",
    response_model=list[WorkflowStepResponse],
)
async def list_for_workflow(
    db: DbSessionDep,
    workflow: OwnedWorkflowDep,
    steps: WorkflowStepRepositoryDep,
):
    return await steps.list_for_workflow(
        db, 
        workflow.id,
    )

# -------------------------------------------------
# DELETE WORKFLOW STEP
# -------------------------------------------------
@router.delete(
    "/steps/{step_id}", 
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_step(
    db: DbSessionDep,
    step: OwnedWorkflowStepDep,
    service: WorkflowStepUpdateServiceDep,
):
    await service.delete(db, step)
