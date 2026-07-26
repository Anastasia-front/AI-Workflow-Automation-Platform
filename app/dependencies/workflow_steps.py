from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.repositories import get_workflow_step_repository
from app.models import User
from app.repositories import WorkflowStepRepository


async def get_owned_workflow_step(
    step_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    steps: Annotated[WorkflowStepRepository, Depends(get_workflow_step_repository)],
):
    step = await steps.get_for_user(db, step_id, user.id)

    if not step:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow step not found",
        )

    # Keep ownership failures indistinguishable from missing resources so API
    # callers cannot infer whether another user's workflow step exists.
    if step.workflow.project.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow step not found",
        )

    return step
