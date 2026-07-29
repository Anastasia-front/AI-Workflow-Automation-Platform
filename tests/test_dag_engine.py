from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.workflow.dag_engine import DAGEngine


def _step(id, depends_on=None, condition=None):
    return SimpleNamespace(
        id=id,
        depends_on=depends_on or [],
        step_order=id,
        name=f"Step {id}",
        prompt_template="Do the thing.\n\n{{input}}",
        condition=condition,
    )


def _build_engine(steps):
    engine = DAGEngine(events=AsyncMock())
    engine.events = AsyncMock()
    engine.steps = SimpleNamespace(list_for_workflow=AsyncMock(return_value=steps))
    engine.step_runs = SimpleNamespace(
        list_completed_for_run=AsyncMock(return_value=[]),
        get_step_run=AsyncMock(return_value=None),
        create=AsyncMock(),
        flush=AsyncMock(),
    )
    engine.runs = AsyncMock()
    engine.executor = SimpleNamespace(execute=AsyncMock())
    return engine


@pytest.mark.asyncio
async def test_execute_raises_when_workflow_has_no_steps():
    engine = _build_engine(steps=[])

    with pytest.raises(Exception, match="Workflow has no steps configured"):
        await engine.execute(
            db=AsyncMock(),
            workflow_run=SimpleNamespace(id=1),
            workflow_id=1,
            user_input="hello",
            max_retries=1,
            continue_on_error=True,
        )


@pytest.mark.asyncio
async def test_execute_raises_when_all_terminal_steps_fail():
    steps = [_step(1), _step(2, depends_on=[1])]

    async def failing_result(step, **kwargs):
        return {
            "step_id": step.id,
            "step_order": step.step_order,
            "prompt": step.prompt_template,
            "success": False,
            "output": None,
            "execution_time_ms": 5,
            "retry_count": 1,
            "error_message": "All connection attempts failed",
        }

    engine = _build_engine(steps=steps)
    engine.executor.execute = AsyncMock(side_effect=failing_result)

    with pytest.raises(Exception, match="All terminal steps failed"):
        await engine.execute(
            db=AsyncMock(),
            workflow_run=SimpleNamespace(id=1),
            workflow_id=1,
            user_input="hello",
            max_retries=1,
            continue_on_error=True,
        )


@pytest.mark.asyncio
async def test_execute_returns_output_when_terminal_step_succeeds():
    steps = [_step(1), _step(2, depends_on=[1])]

    async def result_for(step, **kwargs):
        if step.id == 1:
            return {
                "step_id": 1,
                "step_order": 1,
                "prompt": step.prompt_template,
                "success": False,
                "output": None,
                "execution_time_ms": 5,
                "retry_count": 1,
                "error_message": "All connection attempts failed",
            }
        return {
            "step_id": 2,
            "step_order": 2,
            "prompt": step.prompt_template,
            "success": True,
            "output": "final structured output",
            "execution_time_ms": 5,
            "retry_count": 0,
            "error_message": None,
        }

    engine = _build_engine(steps=steps)
    engine.executor.execute = AsyncMock(side_effect=result_for)

    output = await engine.execute(
        db=AsyncMock(),
        workflow_run=SimpleNamespace(id=1),
        workflow_id=1,
        user_input="hello",
        max_retries=1,
        continue_on_error=True,
    )

    assert output == "final structured output"
