from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chat, Project


class ChatRepository:

    async def create(
            self,
            db: AsyncSession,
            chat: Chat,
        ):
            db.add(chat)

            await db.flush()

            return chat

    async def get_for_user(
        self,
        db: AsyncSession,
        chat_id: int,
        user_id: int,
    ):
        result = await db.execute(
            select(Chat)
            .join(
                Project,
                Project.id == Chat.project_id,
            )
            .where(
                Chat.id == chat_id,
                Project.user_id == user_id,
            )
        )

        return result.scalar_one_or_none()

    async def list_for_project(
        self,
        db: AsyncSession,
        project_id: int,
        user_id: int,
    ):
        result = await db.execute(
            select(Chat)
            .join(
                Project,
                Project.id == Chat.project_id,
            )
            .where(
                Chat.project_id == project_id,
                Project.user_id == user_id,
            )
        )

        return result.scalars().all()
    
    async def delete(
        self,
        db: AsyncSession,
        chat: Chat,
    ):
        await db.delete(chat)

        await db.flush()

    async def update_name(
        self,
        db: AsyncSession,
        chat: Chat,
        name: str,
    ):
        chat.title = name
        await db.flush()
        await db.refresh(chat)

        return chat
