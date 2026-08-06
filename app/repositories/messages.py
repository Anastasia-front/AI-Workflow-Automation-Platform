from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chat, Message, Project


class MessageRepository:

    async def create(
        self,
        db: AsyncSession,
        message: Message
    ):
        db.add(message)
        await db.flush()

        return message

    async def create_committed(
        self,
        db: AsyncSession,
        message: Message,
    ):
        db.add(message)
        await db.commit()
        await db.refresh(message)
        return message

    async def get_by_id(
        self,
        db: AsyncSession,
        message_id: int,
    ):
        result = await db.execute(
            select(Message).where(
                Message.id == message_id
            )
        )

        return result.scalar_one_or_none()

    async def get_for_user(
        self,
        db: AsyncSession,
        message_id: int,
        user_id: int,
    ):
        result = await db.execute(
            select(Message)
            .join(Chat, Chat.id == Message.chat_id)
            .join(Project, Project.id == Chat.project_id)
            .where(
                Message.id == message_id,
                Project.user_id == user_id,
            )
        )

        return result.scalar_one_or_none()

    async def list_for_chat(
        self,
        db: AsyncSession,
        chat_id: int,
    ):
        result = await db.execute(
            select(Message)
            .where(
                Message.chat_id == chat_id
            )
            .order_by(Message.created_at)
        )

        return result.scalars().all()

    async def previous_user_message(
        self,
        db: AsyncSession,
        message: Message,
    ):
        # Compare by id, not created_at: Postgres now() is the transaction
        # timestamp, so a user/assistant pair inserted in the same
        # transaction share an identical created_at.
        result = await db.execute(
            select(Message)
            .where(
                Message.chat_id == message.chat_id,
                Message.role == "user",
                Message.id < message.id,
            )
            .order_by(Message.id.desc())
            .limit(1)
        )

        return result.scalar_one_or_none()

    async def latest_user_message_for_chat(
        self,
        db: AsyncSession,
        chat_id: int,
    ):
        result = await db.execute(
            select(Message)
            .where(
                Message.chat_id == chat_id,
                Message.role == "user",
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )

        return result.scalar_one_or_none()

    async def delete(
        self,
        db: AsyncSession,
        message: Message,
    ):
        await db.delete(message)

        await db.flush()

    async def commit_pair(
        self,
        db: AsyncSession,
        first: Message,
        second: Message,
    ) -> tuple[Message, Message]:
        await db.commit()
        await db.refresh(first)
        await db.refresh(second)
        return first, second
