from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Workflow, WorkflowRun, WorkflowRunEvent


class WorkflowEventRepository:

    async def create(
        self,
        db: AsyncSession,
        workflow_run_id: int,
        event_type: str,
        payload: dict,
    ):

        event = WorkflowRunEvent(
            workflow_run_id=workflow_run_id,
            event_type=event_type,
            payload=payload,
        )

        db.add(event)

        await db.flush()

        return event
    
    async def get_run(
        self,
        db: AsyncSession,
        run_id: int,
    ):
        result = await db.execute(
            select(WorkflowRun).where(
                WorkflowRun.id == run_id,
            )
        )

        return result.scalar_one_or_none()

    async def get_for_user_run(
        self,
        db: AsyncSession,
        run_id: int,
        user_id: int,
    ):
        result = await db.execute(
            select(WorkflowRunEvent)
            .join(
                WorkflowRun,
                WorkflowRun.id == WorkflowRunEvent.workflow_run_id,
            )
            .join(
                Workflow,
                Workflow.id == WorkflowRun.workflow_id,
            )
            .join(
                Project,
                Project.id == Workflow.project_id,
            )
            .where(
                WorkflowRunEvent.workflow_run_id == run_id,
                Project.user_id == user_id,
            )
            .order_by(WorkflowRunEvent.created_at)
        )

        return result.scalars().all()

    async def get_for_run(
        self,
        db: AsyncSession,
        run_id: int,
    ):
        result = await db.execute(
            select(WorkflowRunEvent)
            .where(
                WorkflowRunEvent.workflow_run_id == run_id
            )
            .order_by(
                WorkflowRunEvent.created_at
            )
        )

        return result.scalars().all()

    async def get_after_id(
        self,
        db: AsyncSession,
        run_id: int,
        after_id: int,
    ):
        result = await db.execute(
            select(WorkflowRunEvent)
            .where(
                WorkflowRunEvent.workflow_run_id == run_id,
                WorkflowRunEvent.id > after_id,
            )
            .order_by(
                WorkflowRunEvent.id
            )
        )

        return result.scalars().all()