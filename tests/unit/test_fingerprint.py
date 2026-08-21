from __future__ import annotations

from sports_intelligence.providers.dto import canonical_request_fingerprint


def test_fingerprint_is_stable_for_same_parameters() -> None:
    params = {"date": "2026-08-21", "timezone": "Europe/Warsaw"}
    first = canonical_request_fingerprint("api_football", "fixtures_by_date", params)
    second = canonical_request_fingerprint("api_football", "fixtures_by_date", dict(params))
    assert first == second
    assert first == "api_football:fixtures_by_date:date=2026-08-21&timezone=Europe/Warsaw"


def test_fingerprint_differs_when_timezone_differs() -> None:
    warsaw = canonical_request_fingerprint(
        "api_football", "fixtures_by_date", {"date": "2026-08-21", "timezone": "Europe/Warsaw"}
    )
    london = canonical_request_fingerprint(
        "api_football", "fixtures_by_date", {"date": "2026-08-21", "timezone": "Europe/London"}
    )
    assert warsaw != london


def test_fingerprint_is_independent_of_parameter_order() -> None:
    ordered = canonical_request_fingerprint(
        "api_football", "fixtures_by_date", {"date": "2026-08-21", "timezone": "Europe/Warsaw"}
    )
    reversed_order = canonical_request_fingerprint(
        "api_football", "fixtures_by_date", {"timezone": "Europe/Warsaw", "date": "2026-08-21"}
    )
    assert ordered == reversed_order


def test_fingerprint_includes_provider_and_endpoint_family() -> None:
    mock = canonical_request_fingerprint("mock", "fixtures_by_date", {"date": "2026-08-21"})
    real = canonical_request_fingerprint("api_football", "fixtures_by_date", {"date": "2026-08-21"})
    assert mock != real
    assert mock == "mock:fixtures_by_date:date=2026-08-21"
