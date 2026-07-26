from fastapi import APIRouter, status

from app.dependencies import (
    AgentRunUpdateServiceDep,
    DbSessionDep,
    OwnedAgentRunDep,
    OwnedWorkflowDep,
)
from app.schemas import (
    AgentRunCreate,
    AgentRunResponse,
)

router = APIRouter()


# -------------------------------------------------
# GET SINGLE AGENT RUN
# -------------------------------------------------
@router.get(
    "/agent_runs/{agent_run_id}",
    response_model=AgentRunResponse,
)
async def get_agent_run(
    agent_run: OwnedAgentRunDep,
):
    return agent_run


# -------------------------------------------------
# CREATE RUN AGENT
# -------------------------------------------------
@router.post(
    "/agent_runs/",
    response_model=AgentRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_agent(
    payload: AgentRunCreate,
    db: DbSessionDep,
    workflow: OwnedWorkflowDep,
    service: AgentRunUpdateServiceDep,
):
    return await service.create(db=db, payload=payload, workflow=workflow)
