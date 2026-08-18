from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class ProviderConfig(TimestampMixin, Base):
    __tablename__ = "provider_configs"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "kind", "provider", name="uq_provider_configs_user_kind_provider"
        ),
        Index(
            "uq_provider_configs_kind_provider_default",
            "kind",
            "provider",
            unique=True,
            postgresql_where=text("user_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )
    # NULL means the system-wide default config for this kind/provider,
    # used as a fallback for users who haven't set their own.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    kind: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    model: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    fallback_model: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    base_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    encrypted_api_key: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    dimensions: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
