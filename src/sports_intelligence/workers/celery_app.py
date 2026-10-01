from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from kombu import Queue

from sports_intelligence.core.config import Settings, get_settings

QUEUE_NAMES = ("control", "sports_io", "research_io", "llm", "evaluation", "notifications")


def create_celery_app(settings: Settings) -> Celery:
    beat_schedule: dict[str, dict[str, object]] = {}
    if settings.scheduler_enabled:
        # Celery resolves schedule times in `app.conf.timezone`
        # (configured below to APP_TIMEZONE); crontab itself does not
        # take a timezone parameter.
        #
        # Beat NEVER schedules the discovery worker directly — it
        # targets the argument-free `sports.schedule_discovery(slot)`
        # wrapper which builds the proper Job row and enqueues the full
        # immutable execution tuple (M4.1 §1). Morning and refresh are
        # distinct slots, so the 13:00 refresh cannot be suppressed by
        # the successful 09:00 run.
        beat_schedule["discovery.morning"] = {
            "task": "sports.schedule_discovery",
            "schedule": crontab(
                hour=settings.scheduler_discovery_morning_hour,
                minute=settings.scheduler_discovery_morning_minute,
            ),
            "args": ["morning"],
            "options": {"queue": "control"},
        }
        beat_schedule["discovery.refresh"] = {
            "task": "sports.schedule_discovery",
            "schedule": crontab(
                hour=settings.scheduler_discovery_refresh_hour,
                minute=settings.scheduler_discovery_refresh_minute,
            ),
            "args": ["refresh"],
            "options": {"queue": "control"},
        }
        if settings.scheduler_pre_match_scan_enabled:
            beat_schedule["pre_match.scan"] = {
                "task": "sports.pre_match_scan",
                "schedule": crontab(minute=settings.scheduler_pre_match_scan_cron),
                "options": {"queue": "control"},
            }

    application = Celery(
        "sports_intelligence",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=[
            "sports_intelligence.workers.tasks.control",
            "sports_intelligence.workers.tasks.sports",
            "sports_intelligence.workers.tasks.pre_match",
            "sports_intelligence.workers.tasks.scheduling",
            "sports_intelligence.workers.tasks.research",
            "sports_intelligence.workers.tasks.context",
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
            "sports_intelligence.workers.tasks.context.*": {"queue": "evaluation"},
            "sports_intelligence.workers.tasks.llm.*": {"queue": "llm"},
            "sports_intelligence.workers.tasks.evaluation.*": {"queue": "evaluation"},
            "sports_intelligence.workers.tasks.notifications.*": {"queue": "notifications"},
        },
        task_track_started=True,
        broker_connection_retry_on_startup=True,
        beat_schedule=beat_schedule,
    )
    return application


celery_app = create_celery_app(get_settings())
