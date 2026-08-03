import json
from asyncio import Queue
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from app.core import (
    ENV_SECRET_ASSIGNMENT_RE,
    GOOGLE_API_KEY_RE,
    QUERY_SECRET_RE,
    SECRET_ASSIGNMENT_RE,
    SENSITIVE_FIELD_RE,
)
from app.repositories import (
    WorkflowEventRepository,
)


def redact_secrets(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if SENSITIVE_FIELD_RE.search(str(key)):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = redact_secrets(item)
        return redacted

    if isinstance(value, list):
        return [redact_secrets(item) for item in value]

    if isinstance(value, str):
        redacted = QUERY_SECRET_RE.sub(r"\g<prefix>[redacted]", value)
        redacted = ENV_SECRET_ASSIGNMENT_RE.sub(
            lambda match: f"{match.group('prefix')}{match.group('quote')}[redacted]",
            redacted,
        )
        redacted = SECRET_ASSIGNMENT_RE.sub(
            lambda match: f"{match.group('prefix')}{match.group('quote')}[redacted]",
            redacted,
        )
        return GOOGLE_API_KEY_RE.sub("[redacted]", redacted)

    return value


class EventBus:
    _subscribers = defaultdict(set)

    EVENT_ALIASES = {
        "workflow_queued": "queued",
        "workflow_started": "started",
        "workflow_done": "completed",
        "workflow_failed": "failed",
        "workflow_cancelled": "cancelled",
        "step_start": "step_started",
        "step_done": "step_completed",
        "step_error": "step_failed",
        "step_skipped": "step_skipped",
        "tool_invoked": "tool_invoked",
        "retrieval_started": "retrieval_started",
        "retrieval_completed": "retrieval_completed",
        "partial_output": "partial_output",
    }

    def __init__(self):
        self.repo = WorkflowEventRepository()

    @asynccontextmanager
    async def subscribe(self, workflow_run_id):
        queue = Queue()
        subscribers = self._subscribers[workflow_run_id]
        subscribers.add(queue)
        try:
            yield queue
        finally:
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(workflow_run_id, None)

    async def emit(
        self,
        db,
        workflow_run_id,
        event_type,
        payload,
    ):
        payload = redact_secrets(payload)
        stored_event = await self.repo.create(
            db=db,
            workflow_run_id=workflow_run_id,
            event_type=event_type,
            payload=payload,
        )

        frame = self.format_frame(
            workflow_run_id=workflow_run_id,
            event_type=event_type,
            payload=payload,
            event_id=stored_event.id,
            timestamp=datetime.now(timezone.utc),
        )

        for queue in list(self._subscribers.get(workflow_run_id, ())):
            await queue.put(frame)

        return frame

    @classmethod
    def format_frame(cls, workflow_run_id, event_type, payload, event_id=None, timestamp=None):
        event_name = cls.EVENT_ALIASES.get(event_type, event_type)
        data = {
            "event": event_name,
            "event_type": event_type,
            "run_id": workflow_run_id,
            "message": payload.get("message") or cls._message_for(event_name, payload),
            "progress": payload.get("progress"),
            "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
            **payload,
        }
        if event_id:
            data["event_id"] = event_id

        return f"event: {event_name}\n" f"data: {json.dumps(data)}\n\n"

    @staticmethod
    def _message_for(event_name, payload):
        step_name = payload.get("step_name") or payload.get("name")
        if event_name == "queued":
            return "Workflow queued"
        if event_name == "started":
            return "Workflow started"
        if event_name == "step_started":
            return f"Started {step_name}" if step_name else "Step started"
        if event_name == "step_completed":
            return f"Completed {step_name}" if step_name else "Step completed"
        if event_name == "step_failed":
            return f"Failed {step_name}" if step_name else "Step failed"
        if event_name == "completed":
            return "Workflow completed"
        if event_name == "failed":
            return payload.get("error") or "Workflow failed"
        if event_name == "cancelled":
            return "Workflow cancelled"
        return event_name.replace("_", " ").title()
