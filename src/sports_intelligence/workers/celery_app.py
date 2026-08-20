from __future__ import annotations

from celery import Celery
from kombu import Queue

from sports_intelligence.core.config import Settings, get_settings

QUEUE_NAMES = ("control", "sports_io", "research_io", "llm", "evaluation", "notifications")


def create_celery_app(settings: Settings) -> Celery:
    application = Celery(
        "sports_intelligence",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=[
            "sports_intelligence.workers.tasks.control",
            "sports_intelligence.workers.tasks.sports",
        ],
    )
    application.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone=settings.app_timezone,
        enable_utc=True,
        task_default_queue="control",
        task_queues=tuple(Queue(name) for name in QUEUE_NAMES),
        task_routes={
            "sports_intelligence.workers.tasks.control.*": {"queue": "control"},
            "sports_intelligence.workers.tasks.sports.*": {"queue": "sports_io"},
            "sports_intelligence.workers.tasks.research.*": {"queue": "research_io"},
            "sports_intelligence.workers.tasks.llm.*": {"queue": "llm"},
            "sports_intelligence.workers.tasks.evaluation.*": {"queue": "evaluation"},
            "sports_intelligence.workers.tasks.notifications.*": {"queue": "notifications"},
        },
        task_track_started=True,
        broker_connection_retry_on_startup=True,
        beat_schedule={},
    )
    return application


celery_app = create_celery_app(get_settings())
