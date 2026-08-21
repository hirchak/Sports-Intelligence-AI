from __future__ import annotations

import pytest

from sports_intelligence.core.config import Settings


def _settings(token: str) -> Settings:
    return Settings(
        _env_file=None,
        app_env="mock",
        app_timezone="Europe/Warsaw",
        telegram_bot_token=token,
        telegram_allowed_user_ids=[1],
    )


async def test_run_raises_system_exit_when_token_missing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from sports_intelligence.bot import __main__ as bot_main

    monkeypatch.setattr(bot_main, "get_settings", lambda: _settings(""))
    monkeypatch.setattr(bot_main, "setup_logging", lambda level: None)

    with caplog.at_level("ERROR"), pytest.raises(SystemExit) as exc_info:
        await bot_main.run()
    assert exc_info.value.code == 1
    # The startup refusal message must be a static string and must NEVER
    # include any token (or settings/database URL fragment).
    assert "TELEGRAM_BOT_TOKEN is not configured" in caplog.text
    # Inspect only the message body of every captured record (not the
    # logger name, which legitimately contains "sports_intelligence").
    for record in caplog.records:
        assert "sports_intel" not in record.getMessage()
        assert "postgres" not in record.getMessage()


def test_main_propagates_system_exit_for_missing_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sports_intelligence.bot import __main__ as bot_main

    async def fake_run() -> None:
        raise SystemExit(1)

    monkeypatch.setattr(bot_main, "run", fake_run)

    with pytest.raises(SystemExit) as exc_info:
        bot_main.main()
    assert exc_info.value.code == 1


def test_main_suppresses_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sports_intelligence.bot import __main__ as bot_main

    async def fake_run() -> None:
        raise KeyboardInterrupt()

    monkeypatch.setattr(bot_main, "run", fake_run)

    # Normal Ctrl+C must not surface as an exception from main().
    bot_main.main()
