from __future__ import annotations

from datetime import datetime

from sports_intelligence.core.config import Settings
from sports_intelligence.workers.celery_app import QUEUE_NAMES, create_celery_app
from sports_intelligence.workers.tasks.control import ping


def _settings(**overrides: object) -> Settings:
    kwargs: dict[str, object] = {
        "_env_file": None,
        "app_env": "mock",
        "app_timezone": "Europe/Warsaw",
        "celery_broker_url": "redis://broker-host:6379/0",
        "celery_result_backend": "redis://broker-host:6379/1",
    }
    kwargs.update(overrides)
    return Settings(**kwargs)  # type: ignore[arg-type]


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


def test_beat_schedule_is_empty_by_default() -> None:
    """scheduler_enabled=False (default) keeps the beat schedule empty:
    automatic scheduling never burns free quota during development."""
    application = create_celery_app(_settings())
    assert application.conf.beat_schedule == {}


def test_beat_schedule_morning_at_09_00_warsaw_when_enabled() -> None:
    settings = _settings(scheduler_enabled=True)
    application = create_celery_app(settings)
    schedule = application.conf.beat_schedule
    assert "discovery.morning" in schedule
    entry = schedule["discovery.morning"]
    assert entry["task"] == "sports.discover_fixtures"
    assert entry["options"]["queue"] == "sports_io"
    morning = entry["schedule"]
    assert 9 in morning.hour
    assert 0 in morning.minute


def test_beat_schedule_refresh_at_13_00_when_enabled() -> None:
    settings = _settings(
        scheduler_enabled=True,
        scheduler_discovery_refresh_hour=13,
        scheduler_discovery_refresh_minute=0,
    )
    application = create_celery_app(settings)
    refresh = application.conf.beat_schedule["discovery.refresh"]
    assert refresh["task"] == "sports.discover_fixtures"
    assert refresh["options"]["queue"] == "sports_io"
    assert 13 in refresh["schedule"].hour
    assert 0 in refresh["schedule"].minute


def test_beat_schedule_pre_match_scan_added_when_enabled() -> None:
    settings = _settings(
        scheduler_enabled=True,
        scheduler_pre_match_scan_enabled=True,
        scheduler_pre_match_scan_cron="*/15",
    )
    application = create_celery_app(settings)
    schedule = application.conf.beat_schedule
    assert "pre_match.scan" in schedule
    assert schedule["pre_match.scan"]["task"] == "sports.pre_match_scan"
    assert 0 in schedule["pre_match.scan"]["schedule"].minute
    assert 15 in schedule["pre_match.scan"]["schedule"].minute
    assert 30 in schedule["pre_match.scan"]["schedule"].minute
    assert 45 in schedule["pre_match.scan"]["schedule"].minute


def test_beat_schedule_pre_match_scan_omitted_by_default() -> None:
    """scheduler_pre_match_scan_enabled defaults to False: even when the
    master scheduler is enabled, the pre-match scan stays off until
    explicitly enabled (spec: prevent unnecessary requests)."""
    settings = _settings(scheduler_enabled=True)
    application = create_celery_app(settings)
    assert "pre_match.scan" not in application.conf.beat_schedule


def test_beat_schedule_respects_configured_hours_and_minutes() -> None:
    settings = _settings(
        scheduler_enabled=True,
        scheduler_discovery_morning_hour=8,
        scheduler_discovery_morning_minute=30,
        scheduler_discovery_refresh_hour=14,
        scheduler_discovery_refresh_minute=15,
    )
    application = create_celery_app(settings)
    schedule = application.conf.beat_schedule
    assert 8 in schedule["discovery.morning"]["schedule"].hour
    assert 30 in schedule["discovery.morning"]["schedule"].minute
    assert 14 in schedule["discovery.refresh"]["schedule"].hour
    assert 15 in schedule["discovery.refresh"]["schedule"].minute


def test_beat_schedule_dst_aware_via_app_timezone() -> None:
    """Schedule entries are crontab objects tied to the configured
    APP_TIMEZONE (Europe/Warsaw). Celery applies the timezone via
    `app.conf.timezone` and crontab's tzinfo, so DST transitions are
    handled by the broker/beat process at runtime — the configured
    times stay 09:00 / 13:00 local year-round."""
    settings = _settings(
        scheduler_enabled=True,
        app_timezone="Europe/Warsaw",
    )
    application = create_celery_app(settings)
    assert application.conf.timezone == "Europe/Warsaw"
    morning = application.conf.beat_schedule["discovery.morning"]["schedule"]
    # crontab is timezone-aware; the actual offset is resolved by
    # Celery against conf.timezone at trigger time.
    assert 9 in morning.hour
    assert 0 in morning.minute


def test_ping_task_runs_locally_and_is_registered() -> None:
    application = create_celery_app(_settings())
    assert "control.ping" in application.tasks
    result = ping.run(correlation_id="corr-1")
    assert result["pong"] is True
    assert result["correlation_id"] == "corr-1"
    assert "timestamp" in result


_ = datetime
