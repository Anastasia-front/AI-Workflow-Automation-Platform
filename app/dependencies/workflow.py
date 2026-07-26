from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.repositories import (
    get_workflow_repository,
)
from app.models import User
from app.repositories import (
    WorkflowRepository,
)


async def get_owned_workflow(
    workflow_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    workflows: WorkflowRepository = Depends(get_workflow_repository),
):
    workflow = await workflows.get_for_user(
        db,
        workflow_id,
        user.id,
    )

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        )

    return workflow
