from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProviderConfig


class ProviderConfigRepository:
    async def list_all(
        self,
        db: AsyncSession,
        user_id: int | None,
    ) -> list[ProviderConfig]:
        """Global default rows (user_id IS NULL) plus this user's overrides."""
        result = await db.execute(
            select(ProviderConfig).where(
                (ProviderConfig.user_id.is_(None)) | (ProviderConfig.user_id == user_id)
            )
        )
        return list(result.scalars().all())

    async def get_own(
        self,
        db: AsyncSession,
        kind: str,
        provider: str,
        user_id: int | None,
    ) -> ProviderConfig | None:
        """The row that literally belongs to `user_id` (or the global
        default when `user_id` is None) -- no fallback. Used to find the
        write target for an update, where falling back to someone else's
        (or the global) row would mean mutating it instead of creating the
        caller's own override."""
        result = await db.execute(
            select(ProviderConfig).where(
                ProviderConfig.kind == kind,
                ProviderConfig.provider == provider,
                ProviderConfig.user_id == user_id
                if user_id is not None
                else ProviderConfig.user_id.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def add(self, db: AsyncSession, row: ProviderConfig) -> ProviderConfig:
        db.add(row)
        await db.flush()
        return row

    async def commit(self, db: AsyncSession) -> None:
        await db.commit()
