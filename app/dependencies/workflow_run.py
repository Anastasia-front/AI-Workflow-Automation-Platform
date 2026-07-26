from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.repositories import get_workflow_run_repository
from app.models import User, WorkflowRun
from app.repositories import WorkflowRunRepository


async def get_owned_workflow_run(
    run_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    runs: Annotated[
        WorkflowRunRepository,
        Depends(get_workflow_run_repository),
    ],
) -> WorkflowRun:
    workflow_run = await runs.get_for_user(
        db=db,
        run_id=run_id,
        user_id=user.id,
    )

    if workflow_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    return workflow_run
