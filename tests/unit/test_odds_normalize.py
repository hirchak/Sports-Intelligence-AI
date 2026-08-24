from __future__ import annotations

from decimal import Decimal

import pytest

from sports_intelligence.providers.errors import ProviderResponseError
from sports_intelligence.providers.odds.parse import parse_odds_response


def _payload(*, bookmakers=(), last_update=None, event_id="evt-1", home="Arsenal", away="Coventry"):
    return {
        "id": event_id,
        "sport_key": "soccer_epl",
        "sport_title": "EPL",
        "commence_time": "2026-08-21T12:00:00Z",
        "home_team": home,
        "away_team": away,
        "last_update": last_update,
        "bookmakers": list(bookmakers),
    }


def _bookmaker(*, key="sportsbook", markets=()):
    return {
        "key": key,
        "title": "Sportsbook",
        "last_update": "2026-08-21T10:00:00Z",
        "markets": list(markets),
    }


def test_parse_odds_response_maps_h2h_to_canonical() -> None:
    payload = _payload(
        bookmakers=[
            _bookmaker(
                markets=[
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Arsenal", "price": 2.10},
                            {"name": "Draw", "price": 3.40},
                            {"name": "Coventry", "price": 3.60},
                        ],
                    }
                ]
            )
        ],
        last_update="2026-08-21T10:00:00Z",
    )
    result = parse_odds_response(
        payload, fixture_id="fixture-1", markets=["h2h"], provider="theoddsapi"
    )
    by_selection = {(p.market, p.selection): p.decimal_odds for p in result.prices}
    assert (("h2h_1x2", "home")) in by_selection
    assert (("h2h_1x2", "draw")) in by_selection
    assert (("h2h_1x2", "away")) in by_selection
    assert by_selection[("h2h_1x2", "home")] == Decimal("2.10")


def test_parse_odds_response_maps_totals_by_point() -> None:
    payload = _payload(
        bookmakers=[
            _bookmaker(
                markets=[
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over 1.5", "price": 1.25, "point": 1.5},
                            {"name": "Under 1.5", "price": 3.85, "point": 1.5},
                            {"name": "Over 2.5", "price": 1.85, "point": 2.5},
                            {"name": "Under 2.5", "price": 1.95, "point": 2.5},
                        ],
                    }
                ]
            )
        ]
    )
    result = parse_odds_response(
        payload, fixture_id="fixture-1", markets=["totals"], provider="theoddsapi"
    )
    markets = {p.market for p in result.prices}
    assert markets == {"ou_15", "ou_25"}
    for p in result.prices:
        if p.market == "ou_15":
            assert p.line is not None and float(p.line) == 1.5


def test_parse_odds_response_maps_double_chance_and_btts() -> None:
    payload = _payload(
        bookmakers=[
            _bookmaker(
                markets=[
                    {
                        "key": "double_chance",
                        "outcomes": [
                            {"name": "HomeOrDraw", "price": 1.30},
                            {"name": "HomeOrAway", "price": 1.25},
                            {"name": "DrawOrAway", "price": 1.85},
                        ],
                    },
                    {
                        "key": "btts",
                        "outcomes": [
                            {"name": "Yes", "price": 1.75},
                            {"name": "No", "price": 2.05},
                        ],
                    },
                ]
            )
        ]
    )
    result = parse_odds_response(
        payload,
        fixture_id="fixture-1",
        markets=["double_chance", "btts"],
        provider="theoddsapi",
    )
    selections = {(p.market, p.selection) for p in result.prices}
    assert ("double_chance", "home_or_draw") in selections
    assert ("double_chance", "draw_or_away") in selections
    assert ("btts", "yes") in selections
    assert ("btts", "no") in selections


def test_parse_odds_response_skips_unknown_market_when_not_whitelisted() -> None:
    payload = _payload(
        bookmakers=[
            _bookmaker(
                markets=[
                    {
                        "key": "spreads",
                        "outcomes": [
                            {"name": "Arsenal", "price": 1.91, "point": -0.5},
                            {"name": "Coventry", "price": 1.91, "point": 0.5},
                        ],
                    },
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Arsenal", "price": 2.10},
                            {"name": "Draw", "price": 3.40},
                            {"name": "Coventry", "price": 3.60},
                        ],
                    },
                ]
            )
        ]
    )
    result = parse_odds_response(
        payload, fixture_id="fixture-1", markets=["h2h"], provider="theoddsapi"
    )
    assert all(p.market == "h2h_1x2" for p in result.prices)


def test_parse_odds_response_rejects_malformed_payload() -> None:
    payload = {"bookmakers": "not-a-list"}
    with pytest.raises(ProviderResponseError):
        parse_odds_response(payload, fixture_id="fixture-1", markets=["h2h"], provider="theoddsapi")


def test_parse_odds_response_rejects_unknown_canonical_outcome() -> None:
    payload = _payload(
        bookmakers=[
            _bookmaker(
                markets=[
                    {
                        "key": "h2h",
                        "outcomes": [{"name": "Surprise", "price": 2.0}],
                    }
                ]
            )
        ]
    )
    result = parse_odds_response(
        payload, fixture_id="fixture-1", markets=["h2h"], provider="theoddsapi"
    )
    assert result.prices == ()


def test_parse_odds_response_deduplicates_repeated_outcomes() -> None:
    payload = _payload(
        bookmakers=[
            _bookmaker(
                key="first",
                markets=[
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Arsenal", "price": 2.10},
                            {"name": "Draw", "price": 3.40},
                            {"name": "Coventry", "price": 3.60},
                        ],
                    }
                ],
            ),
            _bookmaker(
                key="second",
                markets=[
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Arsenal", "price": 2.20},
                            {"name": "Draw", "price": 3.40},
                            {"name": "Coventry", "price": 3.55},
                        ],
                    }
                ],
            ),
        ]
    )
    result = parse_odds_response(
        payload, fixture_id="fixture-1", markets=["h2h"], provider="theoddsapi"
    )
    # Two bookmakers => two prices per (market, selection).
    seen = {(p.market, p.selection) for p in result.prices}
    assert len(seen) == 3
    assert len(result.prices) == 6


def test_parse_odds_response_invalid_decimal_raises() -> None:
    payload = _payload(
        bookmakers=[
            _bookmaker(
                markets=[
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Arsenal", "price": "not-a-number"},
                            {"name": "Draw", "price": 3.40},
                            {"name": "Coventry", "price": 3.60},
                        ],
                    }
                ]
            )
        ]
    )
    with pytest.raises(ProviderResponseError):
        parse_odds_response(payload, fixture_id="fixture-1", markets=["h2h"], provider="theoddsapi")
