from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.repositories import (
    get_project_repository,
)
from app.models import User
from app.repositories import ProjectRepository

projects = ProjectRepository()


async def get_owned_project(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
):
    project = await projects.get_for_user(
        db,
        project_id,
        user.id,
    )

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return project
