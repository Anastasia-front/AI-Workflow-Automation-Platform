from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentRun, Project, Workflow


class AgentRunRepository:

    async def create(self, db: AsyncSession, agent_run: AgentRun):
        db.add(agent_run)

        await db.flush()

        return agent_run

    async def get_by_id(
        self,
        db: AsyncSession,
        agent_run_id: int,
    ):
        result = await db.execute(select(AgentRun).where(AgentRun.id == agent_run_id))

        return result.scalar_one_or_none()

    async def get_for_user(
        self,
        db: AsyncSession,
        agent_run_id: int,
        user_id: int,
    ):
        result = await db.execute(
            select(AgentRun)
            .join(
                Workflow,
                Workflow.id == AgentRun.workflow_id,
            )
            .join(
                Project,
                Project.id == Workflow.project_id,
            )
            .where(
                AgentRun.id == agent_run_id,
                Project.user_id == user_id,
            )
        )

        return result.scalar_one_or_none()

    async def list_for_workflow_run(
        self,
        db: AsyncSession,
        workflow_run_id: int,
    ):
        result = await db.execute(
            select(AgentRun)
            .where(AgentRun.workflow_run_id == workflow_run_id)
            .order_by(AgentRun.id.asc())
        )

        return result.scalars().all()

    async def complete(
        self,
        db: AsyncSession,
        agent_run: AgentRun,
        output: str,
    ):
        agent_run.output = output
        agent_run.status = "completed"

        await db.flush()

    async def fail(
        self,
        db: AsyncSession,
        agent_run: AgentRun,
    ):
        agent_run.status = "failed"

        await db.flush()

    async def delete(
        self,
        db: AsyncSession,
        agent_run: AgentRun,
    ):
        await db.delete(agent_run)

        await db.flush()
