import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.models import (
    Project,
    User,
    Workflow,
    WorkflowRun,
    WorkflowRunEvent,
    WorkflowStep,
)
from app.repositories.projects import ProjectRepository


@pytest.fixture
async def db():
    """Runs against the real dev Postgres DB inside a transaction that is
    always rolled back, so nothing written here is ever persisted."""
    engine = create_async_engine(settings.DATABASE_URL)

    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()

    await engine.dispose()


@pytest.mark.asyncio
async def test_deleting_project_cascades_through_workflow_runs_and_events(db: AsyncSession):
    user = User(email="regression-cascade-test@test.com", hashed_password="x")
    project = Project(name="proj", user=user)
    workflow = Workflow(name="wf", project=project)
    workflow.steps.append(
        WorkflowStep(step_order=1, name="step 1", prompt_template="do it")
    )
    run = WorkflowRun(workflow=workflow, input="hello", status="completed")

    db.add_all([user, project, workflow, run])
    await db.flush()

    run_event = WorkflowRunEvent(
        workflow_run_id=run.id, event_type="started", payload={"foo": "bar"}
    )
    db.add(run_event)
    await db.flush()

    project_id = project.id
    workflow_id = workflow.id
    run_id = run.id
    run_event_id = run_event.id

    repo = ProjectRepository()

    # Before the fix, this raised an IntegrityError (500) because Workflow
    # had no cascading relationship to WorkflowRun.
    await repo.delete(db, project)
    db.expire_all()

    assert await repo.get_by_id(db, project_id) is None
    assert (await db.get(Workflow, workflow_id)) is None
    assert (await db.get(WorkflowRun, run_id)) is None
    assert (await db.get(WorkflowRunEvent, run_event_id)) is None
