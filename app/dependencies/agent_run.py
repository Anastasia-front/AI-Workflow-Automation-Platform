from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.repositories import (
    get_agent_run_repository,
)
from app.models import User
from app.repositories import AgentRunRepository


async def get_owned_agent_run(
    agent_run_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    runs: Annotated[
        AgentRunRepository,
        Depends(
            get_agent_run_repository,
        ),
    ],
):
    agent_run = await runs.get_for_user(
        db,
        agent_run_id,
        user.id,
    )

    if not agent_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent run not found",
        )

    return agent_run
