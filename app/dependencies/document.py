from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.repositories import get_document_repository
from app.models import User
from app.repositories import DocumentRepository


async def get_owned_document(
    document_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    documents: Annotated[
        DocumentRepository,
        Depends(
            get_document_repository,
        ),
    ],
):
    document = await documents.get_for_user(
        db,
        document_id,
        user.id,
    )

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return document
