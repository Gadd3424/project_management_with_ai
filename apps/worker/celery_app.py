from celery import Celery

from apps.api.app.config import get_settings

settings = get_settings()
celery_app = Celery(
    "project_ai_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["apps.worker.tasks"],
)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_time_limit=3600,
    task_soft_time_limit=3300,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "process-user-management-outbox": {
            "task": "process_outbox_events",
            "schedule": 10.0,
        }
    },
)
