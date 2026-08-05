import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.models import WorkflowStep
from app.services.ai import AIService


class AIExecutor:

    def __init__(self):
        self.ai = AIService()

    async def execute(
        self,
        step: WorkflowStep,
        user_input: str,
        dependency_outputs: dict[int, Any],
        max_retries: int,
        continue_on_error: bool,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ):

        prompt = step.prompt_template

        prompt = prompt.replace(
            "{{input}}",
            user_input,
        )

        prompt = prompt.replace(
            "{{dependency_outputs}}",
            json.dumps(dependency_outputs),
        )

        attempt = 0
        success = False
        ai_output = None
        error_message = None

        start = time.time()

        while attempt < max_retries and not success:

            try:

                chunks = []
                async for chunk in self.ai.stream_chat_response(
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ]
                ):
                    chunks.append(chunk)
                    if on_chunk:
                        await on_chunk(chunk)

                ai_output = "".join(chunks)
                success = True

            except Exception as e:

                attempt += 1
                error_message = str(e)

                if (
                    attempt >= max_retries
                    and not continue_on_error
                ):
                    raise

        execution_time_ms = int(
            (time.time() - start) * 1000
        )

        return {
            "step_id": step.id,
            "step_order": step.step_order,
            "step_name": step.name,
            "prompt": prompt,
            "success": success,
            "output": ai_output,
            "execution_time_ms": execution_time_ms,
            "retry_count": attempt,
            "error_message": error_message,
            "dependencies": step.depends_on or [],
        }