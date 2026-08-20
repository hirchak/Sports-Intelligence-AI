from __future__ import annotations

from sports_intelligence.core.config import Settings
from sports_intelligence.workers.celery_app import QUEUE_NAMES, create_celery_app
from sports_intelligence.workers.tasks.control import ping


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="mock",
        celery_broker_url="redis://broker-host:6379/0",
        celery_result_backend="redis://broker-host:6379/1",
    )


def test_celery_broker_and_backend_configured_from_settings() -> None:
    application = create_celery_app(_settings())
    assert application.conf.broker_url == "redis://broker-host:6379/0"
    assert application.conf.result_backend == "redis://broker-host:6379/1"


def test_celery_serialization_and_timezone_config() -> None:
    application = create_celery_app(_settings())
    assert application.conf.task_serializer == "json"
    assert application.conf.accept_content == ["json"]
    assert application.conf.timezone == "Europe/Warsaw"
    assert application.conf.enable_utc is True


def test_celery_queues_cover_agent_catalog_layout() -> None:
    application = create_celery_app(_settings())
    queue_names = {queue.name for queue in application.conf.task_queues}
    assert queue_names == set(QUEUE_NAMES)
    assert application.conf.task_default_queue == "control"


def test_celery_task_routes_are_preconfigured() -> None:
    routes = create_celery_app(_settings()).conf.task_routes
    assert routes["sports_intelligence.workers.tasks.control.*"]["queue"] == "control"
    assert routes["sports_intelligence.workers.tasks.sports.*"]["queue"] == "sports_io"
    assert routes["sports_intelligence.workers.tasks.research.*"]["queue"] == "research_io"
    assert routes["sports_intelligence.workers.tasks.llm.*"]["queue"] == "llm"
    assert routes["sports_intelligence.workers.tasks.evaluation.*"]["queue"] == "evaluation"
    assert routes["sports_intelligence.workers.tasks.notifications.*"]["queue"] == "notifications"


def test_beat_schedule_starts_empty() -> None:
    application = create_celery_app(_settings())
    assert application.conf.beat_schedule == {}


def test_ping_task_runs_locally_and_is_registered() -> None:
    application = create_celery_app(_settings())
    assert "control.ping" in application.tasks
    result = ping.run(correlation_id="corr-1")
    assert result["pong"] is True
    assert result["correlation_id"] == "corr-1"
    assert "timestamp" in result
