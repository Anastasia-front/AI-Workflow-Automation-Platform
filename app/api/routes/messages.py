
from fastapi import APIRouter, status
from starlette.responses import StreamingResponse

from app.dependencies import (
    ChatServiceDep,
    CurrentUserDep,
    DbSessionDep,
    MessageRepositoryDep,
    OwnedChatDep,
)
from app.schemas import (
    MessageCreate,
    MessageResponse,
)

router = APIRouter()


# -------------------------------------------------
# GET MESSAGES
# -------------------------------------------------
@router.get(
    "/{chat_id}/messages",
    response_model=list[MessageResponse],
)
async def get_messages(
    db: DbSessionDep,
    chat: OwnedChatDep,
    messages: MessageRepositoryDep,
):
    return await messages.list_for_chat(
        db,
        chat.id,
    )


# -------------------------------------------------
# CREATE MESSAGE
# -------------------------------------------------
@router.post(
    "/{chat_id}/messages",
    response_model=list[MessageResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    payload: MessageCreate,
    db: DbSessionDep,
    chat: OwnedChatDep,
    user: CurrentUserDep,
    chat_service: ChatServiceDep,
):
    user_msg, assistant_msg = await chat_service.create_message(
        db=db,
        chat=chat,
        user=user,
        content=payload.content,
        agent_name=payload.agent_name,
    )

    return [user_msg, assistant_msg]

# -------------------------------------------------
# STREAM MESSAGE
# -------------------------------------------------
@router.post(
    "/{chat_id}/messages/stream",
)
async def create_message_stream(
    payload: MessageCreate,
    db: DbSessionDep,
    chat: OwnedChatDep,
    user: CurrentUserDep,
    chat_service: ChatServiceDep,
):
    return StreamingResponse(
        chat_service.create_message_stream(
            db=db,
            chat=chat,
            user=user,
            content=payload.content,
            agent_name=payload.agent_name,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

# -------------------------------------------------
# REGENERATE MESSAGE
# -------------------------------------------------
@router.post(
    "/messages/{message_id}/regenerate",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def regenerate_message(
    message_id: int,
    db: DbSessionDep,
    user: CurrentUserDep,
    chat_service: ChatServiceDep,
):
    return await chat_service.regenerate_message(
        db=db,
        message_id=message_id,
        user=user,
    )
