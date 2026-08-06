from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import MAX_RESOURCE_NAME_LENGTH
from app.enums import AgentRunStatus, WorkflowRunStatus
from app.models import AgentRun, Chat, Project, Workflow, WorkflowStep
from app.repositories import (
    AgentRunRepository,
    ChatRepository,
    ProjectRepository,
    WorkflowRepository,
    WorkflowStepRepository,
)
from app.schemas import (
    AgentRunCreate,
    ChatCreate,
    ChatUpdate,
    ProjectCreate,
    ProjectUpdate,
    WorkflowCreate,
    WorkflowStepCreate,
    WorkflowUpdate,
)


def normalize_resource_label(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} cannot be blank.",
        )
    if len(normalized) > MAX_RESOURCE_NAME_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must be {MAX_RESOURCE_NAME_LENGTH} characters or fewer.",
        )

    return normalized


class ProjectUpdateService:
    def __init__(self, projects: ProjectRepository):
        self.projects = projects

    async def update(
        self,
        db: AsyncSession,
        project: Project,
        payload: ProjectUpdate,
    ) -> Project:
        name = normalize_resource_label(payload.name, "Project name")
        if name is not None:
            project = await self.projects.update_name(db, project, name)

        await db.commit()
        await db.refresh(project)
        return project

    async def create(
        self,
        db: AsyncSession,
        *,
        payload: ProjectCreate,
        user_id: int,
    ) -> Project:
        project = Project(
            name=payload.name,
            description=payload.description,
        )
        await self.projects.create(db=db, project=project, user_id=user_id)
        await db.commit()
        await db.refresh(project)
        return project

    async def delete(
        self,
        db: AsyncSession,
        project: Project,
    ) -> None:
        await self.projects.delete(db, project)
        await db.commit()


class ChatUpdateService:
    def __init__(self, chats: ChatRepository):
        self.chats = chats

    async def update(
        self,
        db: AsyncSession,
        chat: Chat,
        payload: ChatUpdate,
    ) -> Chat:
        name = normalize_resource_label(payload.title, "Chat title")
        if name is not None:
            chat = await self.chats.update_name(db, chat, name)

        await db.commit()
        await db.refresh(chat)
        return chat

    async def create(
        self,
        db: AsyncSession,
        *,
        payload: ChatCreate,
        project: Project,
    ) -> Chat:
        chat = Chat(
            project_id=project.id,
            title=payload.title,
            agent_name=payload.agent_name,
        )
        await self.chats.create(db, chat)
        await db.commit()
        await db.refresh(chat)
        return chat

    async def delete(
        self,
        db: AsyncSession,
        chat: Chat,
    ) -> None:
        await self.chats.delete(db, chat)
        await db.commit()


class WorkflowUpdateService:
    def __init__(self, workflows: WorkflowRepository):
        self.workflows = workflows

    async def update(
        self,
        db: AsyncSession,
        workflow: Workflow,
        payload: WorkflowUpdate,
    ) -> Workflow:
        if workflow.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found",
            )

        name = normalize_resource_label(payload.name, "Workflow name")
        if name is not None:
            workflow = await self.workflows.update_name(db, workflow, name)

        await db.commit()
        await db.refresh(workflow)
        return workflow

    async def create(
        self,
        db: AsyncSession,
        *,
        payload: WorkflowCreate,
        project: Project,
    ) -> Workflow:
        workflow = Workflow(
            project_id=project.id,
            name=payload.name,
            status=WorkflowRunStatus.RUNNING,
        )
        await self.workflows.create(db, workflow)
        await db.commit()
        await db.refresh(workflow)
        return workflow

    async def delete(
        self,
        db: AsyncSession,
        workflow: Workflow,
    ) -> None:
        await self.workflows.delete(db, workflow)
        await db.commit()


class WorkflowStepUpdateService:
    def __init__(self, steps: WorkflowStepRepository):
        self.steps = steps

    async def create(
        self,
        db: AsyncSession,
        *,
        payload: WorkflowStepCreate,
        workflow: Workflow,
    ) -> WorkflowStep:
        step = WorkflowStep(
            workflow_id=workflow.id,
            step_order=payload.step_order,
            name=payload.name,
            prompt_template=payload.prompt_template,
            depends_on=payload.depends_on,
            condition=payload.condition,
        )
        await self.steps.create(db, step)
        await db.commit()
        await db.refresh(step)
        return step

    async def delete(
        self,
        db: AsyncSession,
        step: WorkflowStep,
    ) -> None:
        await self.steps.delete(db, step)
        await db.commit()


class AgentRunUpdateService:
    def __init__(self, agent_runs: AgentRunRepository):
        self.agent_runs = agent_runs

    async def create(
        self,
        db: AsyncSession,
        *,
        payload: AgentRunCreate,
        workflow: Workflow,
    ) -> AgentRun:
        agent_run = AgentRun(
            workflow_id=workflow.id,
            goal=payload.goal,
            status=AgentRunStatus.COMPLETED,
            result=f"Agent completed goal: {payload.goal}",
        )
        await self.agent_runs.create(db, agent_run)
        await db.commit()
        await db.refresh(agent_run)
        return agent_run
