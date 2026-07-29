from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import WorkflowRunStatus
from app.models import Project, Workflow, WorkflowRun, WorkflowRunEvent, WorkflowStepRun


class WorkflowRunRepository:
    def _user_runs_filters(
        self,
        user_id: int,
        status: WorkflowRunStatus | None = None,
        project_id: int | None = None,
    ):
        filters = [Project.user_id == user_id]

        if status is not None:
            filters.append(WorkflowRun.status == status)

        if project_id is not None:
            filters.append(Project.id == project_id)

        return filters

    async def create(
        self,
        db: AsyncSession,
        workflow_id: int,
        user_input: str,
    ) -> WorkflowRun:

        workflow_run = WorkflowRun(
            workflow_id=workflow_id,
            input=user_input,
            status=WorkflowRunStatus.PENDING,
        )

        db.add(workflow_run)

        await db.flush()

        return workflow_run

    async def complete(
        self,
        db: AsyncSession,
        workflow_run: WorkflowRun,
        output: str,
    ):

        workflow_run.output = output
        workflow_run.status = WorkflowRunStatus.COMPLETED

        await db.flush()

    async def commit_complete(
        self,
        db: AsyncSession,
        workflow_run: WorkflowRun,
        output: str,
    ) -> WorkflowRun:
        await db.refresh(workflow_run)
        if workflow_run.status == WorkflowRunStatus.CANCELED:
            return workflow_run

        workflow_run.output = output
        workflow_run.status = WorkflowRunStatus.COMPLETED
        await db.commit()
        await db.refresh(workflow_run)
        return workflow_run

    async def fail(
        self,
        db: AsyncSession,
        workflow_run: WorkflowRun,
    ):

        workflow_run.status = WorkflowRunStatus.FAILED

        await db.flush()

    async def create_committed(
        self,
        db: AsyncSession,
        workflow_id: int,
        user_input: str,
    ) -> WorkflowRun:
        workflow_run = await self.create(
            db=db,
            workflow_id=workflow_id,
            user_input=user_input,
        )
        await db.commit()
        await db.refresh(workflow_run)
        return workflow_run

    async def set_task_id(
        self,
        db: AsyncSession,
        workflow_run: WorkflowRun,
        task_id: str,
    ) -> WorkflowRun:
        workflow_run.celery_task_id = task_id
        await db.commit()
        await db.refresh(workflow_run)
        return workflow_run

    async def start(
        self,
        db: AsyncSession,
        workflow_run: WorkflowRun,
    ) -> WorkflowRun:
        workflow_run.status = WorkflowRunStatus.RUNNING
        await db.commit()
        await db.refresh(workflow_run)
        return workflow_run

    async def claim_pending(
        self,
        db: AsyncSession,
        run_id: int,
    ) -> WorkflowRun | None:
        result = await db.execute(
            select(WorkflowRun)
            .where(WorkflowRun.id == run_id)
            .with_for_update()
        )
        workflow_run = result.scalar_one_or_none()

        if workflow_run is None:
            return None

        if workflow_run.status != WorkflowRunStatus.PENDING:
            await db.rollback()
            return None

        workflow_run.status = WorkflowRunStatus.RUNNING
        await db.commit()
        await db.refresh(workflow_run)
        return workflow_run

    async def set_status(
        self,
        db: AsyncSession,
        workflow_run: WorkflowRun,
        status: WorkflowRunStatus,
    ) -> WorkflowRun:
        workflow_run.status = status
        await db.commit()
        await db.refresh(workflow_run)
        return workflow_run

    async def fail_with_error(
        self,
        db: AsyncSession,
        workflow_run: WorkflowRun,
        error: str,
    ) -> WorkflowRun:
        await db.refresh(workflow_run)
        if workflow_run.status == WorkflowRunStatus.CANCELED:
            return workflow_run

        workflow_run.status = WorkflowRunStatus.FAILED
        workflow_run.error = error
        await db.commit()
        await db.refresh(workflow_run)
        return workflow_run

    async def cancel(
        self,
        db: AsyncSession,
        workflow_run: WorkflowRun,
    ) -> WorkflowRun:
        workflow_run.status = WorkflowRunStatus.CANCELED
        workflow_run.error = "Canceled by user."
        await db.commit()
        await db.refresh(workflow_run)
        return workflow_run

    async def fail_committed(
        self,
        db: AsyncSession,
        workflow_run: WorkflowRun,
    ) -> WorkflowRun:
        workflow_run.status = WorkflowRunStatus.FAILED
        await db.commit()
        return workflow_run

    async def get_running(
        self,
        db: AsyncSession,
    ):
        result = await db.execute(
            select(WorkflowRun)
            .where(
                WorkflowRun.status ==  WorkflowRunStatus.RUNNING
            )
        )

        return result.scalars().all()

    async def get_stale(
        self,
        db: AsyncSession,
        older_than: datetime,
    ):
        """RUNNING/PENDING runs whose updated_at is older than the cutoff --
        i.e. a worker likely died mid-run (crash/restart) rather than the
        run still being actively worked on."""
        result = await db.execute(
            select(WorkflowRun).where(
                WorkflowRun.status.in_(
                    [WorkflowRunStatus.PENDING, WorkflowRunStatus.RUNNING]
                ),
                WorkflowRun.updated_at < older_than,
            )
        )

        return result.scalars().all()

    async def get_by_id(
        self,
        db: AsyncSession,
        run_id: int,
    ):
        result = await db.execute(
            select(WorkflowRun).where(
                WorkflowRun.id == run_id
            )
        )

        return result.scalar_one_or_none()
    
    async def get_for_user(
        self,
        db: AsyncSession,
        run_id: int,
        user_id: int,
    ):
        result = await db.execute(
            select(WorkflowRun)
            .join(
                Workflow,
                Workflow.id == WorkflowRun.workflow_id,
            )
            .join(
                Project,
                Project.id == Workflow.project_id,
            )
            .where(
                WorkflowRun.id == run_id,
                Project.user_id == user_id,
            )
        )

        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        db: AsyncSession,
        user_id: int,
        status: WorkflowRunStatus | None = None,
        project_id: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ):
        query = (
            select(WorkflowRun)
            .join(
                Workflow,
                Workflow.id == WorkflowRun.workflow_id,
            )
            .join(
                Project,
                Project.id == Workflow.project_id,
            )
            .where(
                *self._user_runs_filters(user_id, status, project_id),
            )
            .order_by(WorkflowRun.created_at.desc())
        )

        if limit is not None:
            query = query.limit(limit).offset(offset)

        result = await db.execute(query)

        return result.scalars().all()

    async def count_for_user(
        self,
        db: AsyncSession,
        user_id: int,
        status: WorkflowRunStatus | None = None,
        project_id: int | None = None,
    ) -> int:
        result = await db.execute(
            select(func.count(WorkflowRun.id))
            .join(
                Workflow,
                Workflow.id == WorkflowRun.workflow_id,
            )
            .join(
                Project,
                Project.id == Workflow.project_id,
            )
            .where(
                *self._user_runs_filters(user_id, status, project_id),
            )
        )

        return result.scalar_one()

    async def delete(
        self,
        db: AsyncSession,
        workflow_run: WorkflowRun,
    ) -> None:
        await db.execute(
            delete(WorkflowRunEvent).where(
                WorkflowRunEvent.workflow_run_id == workflow_run.id,
            )
        )
        await db.execute(
            delete(WorkflowStepRun).where(
                WorkflowStepRun.workflow_run_id == workflow_run.id,
            )
        )
        await db.delete(workflow_run)
        await db.commit()

    async def delete_for_user_by_status(
        self,
        db: AsyncSession,
        user_id: int,
        status: WorkflowRunStatus,
        project_id: int | None = None,
    ) -> int:
        workflow_runs = await self.list_for_user(
            db=db,
            user_id=user_id,
            status=status,
            project_id=project_id,
        )
        deleted = len(workflow_runs)

        for workflow_run in workflow_runs:
            await db.execute(
                delete(WorkflowRunEvent).where(
                    WorkflowRunEvent.workflow_run_id == workflow_run.id,
                )
            )
            await db.execute(
                delete(WorkflowStepRun).where(
                    WorkflowStepRun.workflow_run_id == workflow_run.id,
                )
            )
            await db.delete(workflow_run)

        await db.commit()
        return deleted
    
    async def get_for_workflow(
        self,
        db: AsyncSession,
        workflow_id: int,
        user_id: int,
    ):
        result = await db.execute(
            select(WorkflowRun)
            .join(
                Workflow,
                Workflow.id == WorkflowRun.workflow_id,
            )
            .join(
                Project,
                Project.id == Workflow.project_id,
            )
            .where(
                WorkflowRun.workflow_id == workflow_id,
                Project.user_id == user_id,
            )
            .order_by(WorkflowRun.created_at.desc())
        )

        return result.scalars().all()
