import logging

from celery import Celery

from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# Redis is used purely as the Celery broker. PostgreSQL (via the existing
# SQLAlchemy models/repositories) remains the sole source of truth for job
# status, progress, output and errors -- task results are never relied upon
# by the API or frontend, so no Celery result backend is configured.
celery_app = Celery(
    "ai_platform",
    broker=settings.CELERY_BROKER_URL,
)

celery_app.conf.update(
    task_ignore_result=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    imports=(
        "app.tasks.documents",
        "app.tasks.embeddings",
        "app.tasks.workflows",
    ),
)
