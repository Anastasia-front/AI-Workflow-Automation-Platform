from fastapi import APIRouter, status

from app.dependencies import (
    ChatRepositoryDep,
    ChatUpdateServiceDep,
    CurrentUserDep,
    DbSessionDep,
    OwnedChatDep,
    OwnedProjectDep,
)
from app.schemas import ChatCreate, ChatResponse, ChatUpdate

router = APIRouter()

# -------------------------------------------------
# CREATE CHAT
# -------------------------------------------------
@router.post(
    "/projects/{project_id}/chats",
    response_model=ChatResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat(
    payload: ChatCreate,
    db: DbSessionDep,
    project: OwnedProjectDep,
    service: ChatUpdateServiceDep,
):
    return await service.create(
        db=db,
        payload=payload,
        project=project,
    )

# -------------------------------------------------
# GET SINGLE CHAT
# -------------------------------------------------
@router.get(
    "/chats/{chat_id}",
    response_model=ChatResponse,
)
async def get_chat(
    chat: OwnedChatDep,
):
    return chat


# -------------------------------------------------
# UPDATE CHAT
# -------------------------------------------------
@router.patch(
    "/chats/{chat_id}",
    response_model=ChatResponse,
)
async def update_chat(
    payload: ChatUpdate,
    db: DbSessionDep,
    chat: OwnedChatDep,
    service: ChatUpdateServiceDep,
):
    return await service.update(
        db=db,
        chat=chat,
        payload=payload,
    )

# -------------------------------------------------
# GET PROJECT CHATS
# -------------------------------------------------
@router.get(
    "/projects/{project_id}/chats",
    response_model=list[ChatResponse],
)
async def get_project_chats(
    db: DbSessionDep,
    user: CurrentUserDep,
    project: OwnedProjectDep,
    chats: ChatRepositoryDep,
):
    return await chats.list_for_project(
        db,
        project.id,
        user.id,
    )

# -------------------------------------------------
# DELETE CHAT
# -------------------------------------------------
@router.delete(
    "/chats/{chat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_chat(
    db: DbSessionDep,
    chat: OwnedChatDep,
    service: ChatUpdateServiceDep,
):
    await service.delete(db, chat)
