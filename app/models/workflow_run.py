from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.enums import WorkflowRunStatus
from app.models.mixins import TimestampMixin


class WorkflowRun(TimestampMixin, Base):
    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    workflow_id: Mapped[int] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    input: Mapped[str] = mapped_column(Text, nullable=False)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String,
        default=WorkflowRunStatus.PENDING,
        nullable=False,
    )

    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    workflow = relationship("Workflow", back_populates="runs")
    step_runs = relationship(
        "WorkflowStepRun",
        back_populates="workflow_run",
        cascade="all, delete-orphan",
    )
