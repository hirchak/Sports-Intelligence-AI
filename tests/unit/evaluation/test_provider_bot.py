from datetime import UTC, date, datetime

import httpx
import pytest

from sports_intelligence.bot.backend_client import (
    BackendClient,
    BackendPayloadError,
    BackendResponseError,
)
from sports_intelligence.bot.context import AppContext
from sports_intelligence.bot.evaluation import (
    render_stats,
    stats_callback,
    stats_command,
    stats_keyboard,
)
from sports_intelligence.core.config import Settings
from sports_intelligence.evaluation.settlement import ResultStatus
from sports_intelligence.providers.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderServerError,
    ProviderTimeoutError,
)
from sports_intelligence.providers.sports.api_football import ApiFootballProvider
from sports_intelligence.providers.sports.results import parse_results
from sports_intelligence.workers.celery_app import create_celery_app
from telegram_fakes import FakeTransport, make_callback, make_message


def payload(status="FT", h=1, a=1):
    return {
        "response": [
            {
                "fixture": {"id": 42, "status": {"short": status}},
                "score": {"fulltime": {"home": h, "away": a}},
                "goals": {"home": 99, "away": 99},
            }
        ]
    }


@pytest.mark.parametrize(
    "code,status",
    [
        ("FT", ResultStatus.FINAL),
        ("AET", ResultStatus.AFTER_EXTRA_TIME),
        ("PEN", ResultStatus.AFTER_PENALTIES),
        ("PST", ResultStatus.POSTPONED),
        ("CANC", ResultStatus.CANCELLED),
        ("ABD", ResultStatus.ABANDONED),
        ("2H", ResultStatus.UNFINISHED),
        ("AWD", ResultStatus.UNKNOWN),
    ],
)
def test_status_and_explicit_score_contract(code, status):
    raw = payload(
        code, None if code in ("PST", "CANC") else 1, None if code in ("PST", "CANC") else 1
    )
    result = parse_results(raw, datetime.now(UTC))[0]
    assert result.status == status and result.regulation_home != 99


@pytest.mark.parametrize(
    "raw",
    [
        {"response": "bad"},
        payload("FT", True, 0),
        payload("FT", -1, 0),
        payload("FT", None, 0),
        {"response": [{"fixture": {"id": 42}}]},
        {"response": payload()["response"] * 2},
    ],
)
def test_bad_result_contract_nonretryable(raw):
    with pytest.raises(ProviderResponseError):
        parse_results(raw, datetime.now(UTC))


async def test_one_physical_http_attempt_date_batch_utc_no_fixture_loop():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=payload(), headers={"x-ratelimit-requests-remaining": "12"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = ApiFootballProvider("synthetic-test-key", client=client)
        result = await provider.get_results_by_date(date(2026, 8, 21))
    assert len(calls) == 1 and calls[0].url.params == httpx.QueryParams(
        {"date": "2026-08-21", "timezone": "UTC"}
    )
    assert result.rate_headers["x-ratelimit-requests-remaining"] == "12"
    assert result.raw_payload == payload() and result.results[0].regulation_home == 1


@pytest.mark.parametrize(
    "status,error",
    [
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (429, ProviderRateLimitError),
        (500, ProviderServerError),
        (400, ProviderResponseError),
    ],
)
async def test_http_failures_no_hidden_retry(status, error):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(error):
            await ApiFootballProvider("synthetic", client=client).get_results_by_date(date.today())
    assert len(calls) == 1


async def test_timeout_no_hidden_retry():
    def handle(request):
        raise httpx.ReadTimeout("synthetic", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ProviderTimeoutError):
            await ApiFootballProvider("synthetic", client=client).get_results_by_date(date.today())


def test_beat_opt_in_conservative_window_and_queues():
    assert "results.scan" not in create_celery_app(Settings(_env_file=None)).conf.beat_schedule
    app = create_celery_app(Settings(_env_file=None, result_scan_enabled=True))
    assert app.conf.beat_schedule["results.scan"]["schedule"] == 3600
    assert app.conf.task_routes["evaluation.collect_results"]["queue"] == "sports_io"
    assert app.conf.task_routes["evaluation.evaluate"]["queue"] == "evaluation"
    assert app.conf.task_routes["evaluation.result_scan"]["queue"] == "control"


async def test_telegram_stats_uses_backend_only_and_samples():
    calls = []
    data = {
        "status": "SUCCEEDED",
        "groups": [
            {
                "dimensions": {"role": "PRIMARY", "variant": "LLM_WITH_ODDS", "baseline": "llm"},
                "sample_size": 3,
                "metrics": {
                    "binary_brier": {"value": 0.25, "sample_size": 3},
                    "calibration_ece": {"value": 0.1, "sample_size": 3},
                },
                "calibration": [],
            }
        ],
    }

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=data)

    transport = FakeTransport()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        context = AppContext(
            transport=transport,
            backend=BackendClient("https://synthetic.invalid", client=http),
            settings=Settings(_env_file=None),
            allowed_user_ids=frozenset({1}),
        )
        await stats_command(make_message("/stats"), context)
        await stats_callback(make_callback("stats:7d:market"), context)
    assert len(calls) == 2 and all(r.url.path == "/v1/evaluations/summary" for r in calls)
    assert calls[-1].url.params["group_by"] == "market" and calls[-1].url.params["period"] == "7d"
    assert "n=3" in transport.sent[0]["text"] and "Brier" in transport.edited[0]["text"]
    assert transport.answered
    assert all(
        len(b.callback_data.encode()) <= 64 for row in stats_keyboard().inline_keyboard for b in row
    )


async def test_backend_failure_safe():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(503))
    ) as http:
        backend = BackendClient("https://synthetic.invalid", client=http)
        with pytest.raises(BackendResponseError):
            await backend.evaluation_summary()
    assert "0" in render_stats({"status": "not_available", "groups": []})


async def test_backend_malformed_stats_safe():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"groups": "bad"}))
    ) as http:
        with pytest.raises(BackendPayloadError):
            await BackendClient("https://synthetic.invalid", client=http).evaluation_summary()


@pytest.mark.parametrize("header,expected", [(None, 2), ("12", 12), ("120", None), ("nan", None)])
def test_result_retry_after_respected_or_deferred(header, expected):
    from sports_intelligence.evaluation.results import retry_delay

    error = ProviderRateLimitError(
        "synthetic rate limit", quota_headers={"retry-after": header} if header else {}
    )
    assert retry_delay(error, 0, datetime.now(UTC)) == expected


async def test_nan_backend_metric_rejected():
    data = {
        "status": "SUCCEEDED",
        "groups": [
            {
                "dimensions": {},
                "sample_size": 1,
                "metrics": {"binary_brier": {"value": float("nan"), "sample_size": 1}},
            }
        ],
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, text=__import__("json").dumps(data))
        )
    ) as http:
        with pytest.raises(BackendPayloadError):
            await BackendClient("https://synthetic.invalid", client=http).evaluation_summary()
