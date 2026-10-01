from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sports_intelligence.context.selector import SelectedEvidence, SelectedFixtureInfo
from sports_intelligence.core.phases import ForecastPhase
from sports_intelligence.db.models import (
    AvailabilitySnapshot,
    OddsPrice,
    OddsSnapshotSet,
    StandingSnapshot,
    TeamFormSnapshot,
)
from sports_intelligence.features.builder import build_features


def _fixture_info(kickoff: datetime) -> SelectedFixtureInfo:
    return SelectedFixtureInfo(
        fixture_id=uuid.uuid4(),
        league_id=uuid.uuid4(),
        season_id=uuid.uuid4(),
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
        kickoff_at=kickoff,
        venue="Emirates Stadium",
        round="Regular Season - 1",
        status="NS",
        league_slug="premier-league",
        league_name="Premier League",
        home_team_name="Arsenal",
        away_team_name="Chelsea",
        home_provider_mappings=[],
        away_provider_mappings=[],
        home_provider_external_ids={"api_football": "42"},
        away_provider_external_ids={"api_football": "49"},
    )


def test_hand_calculated_form_features_exact_math() -> None:
    kickoff = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
    fix_info = _fixture_info(kickoff)

    # Synthetic 10-match history for home team:
    # Match 0: 3 days prior, W, 2-0 (home) -> 3 pts, scored, CS
    # Match 1: 6 days prior, W, 3-1 (home) -> 3 pts, scored
    # Match 2: 10 days prior, D, 1-1 (away) -> 1 pt, scored
    # Match 3: 13 days prior, L, 0-2 (away) -> 0 pts, conceded
    # Match 4: 17 days prior, W, 2-1 (home) -> 3 pts, scored
    # (Last 5: W, W, D, L, W -> 10 pts / 5 = 2.0 PPG; GF=8/5=1.6; GA=5/5=1.0)
    # Match 5: 20 days prior, D, 0-0 (home) -> 1 pt, CS
    # Match 6: 24 days prior, W, 1-0 (away) -> 3 pts, scored, CS
    # Match 7: 28 days prior, L, 1-3 (away) -> 0 pts, scored, conceded
    # Match 8: 31 days prior, W, 2-1 (home) -> 3 pts, scored
    # Match 9: 35 days prior, W, 4-0 (home) -> 3 pts, scored, CS
    # (Last 10: 6 W, 2 D, 2 L -> 20 pts / 10 = 2.0 PPG)
    # Total GF = 2+3+1+0+2+0+1+1+2+4 = 16 -> 1.6 GF/match
    # Total GA = 0+1+1+2+1+0+0+3+1+0 = 9 -> 0.9 GA/match
    # Scored in 8 of 10 -> 0.80 scored_rate
    # Conceded in 6 of 10 -> 0.60 conceded_rate
    # Clean sheets in 4 of 10 -> 0.40 clean_sheet_rate
    # Home matches: Match 0, 1, 4, 5, 8, 9 (6 matches)
    # Home outcomes: W(3), W(3), W(3), D(1), W(3), W(3) = 16 pts / 6 = 2.6667 PPG
    days_offsets = [3, 6, 10, 13, 17, 20, 24, 28, 31, 35]
    outcomes_raw = [
        ("W", 2, 0, True),
        ("W", 3, 1, True),
        ("D", 1, 1, False),
        ("L", 0, 2, False),
        ("W", 2, 1, True),
        ("D", 0, 0, True),
        ("W", 1, 0, False),
        ("L", 1, 3, False),
        ("W", 2, 1, True),
        ("W", 4, 0, True),
    ]
    home_outcomes = []
    for (res, gf, ga, is_h), days in zip(outcomes_raw, days_offsets, strict=True):
        m_kickoff = kickoff - timedelta(days=days)
        home_outcomes.append(
            {
                "outcome": res,
                "result": res,
                "goals_for": gf,
                "goals_against": ga,
                "is_home": is_h,
                "kickoff_utc": m_kickoff.isoformat(),
            }
        )

    home_form = TeamFormSnapshot(
        team_id=fix_info.home_team_id,
        as_of=kickoff - timedelta(hours=5),
        window_size=10,
        scope="overall",
        metrics_jsonb={"outcomes": home_outcomes, "window_size": 10},
        source_fingerprint="fp-home-form",
    )

    evidence = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=kickoff - timedelta(hours=5),
        fixture=fix_info,
        standings=None,
        home_team_stats=None,
        away_team_stats=None,
        home_form=home_form,
        away_form=None,
        home_availability=None,
        away_availability=None,
        home_lineup=None,
        away_lineup=None,
        odds_set=None,
    )

    features = build_features(evidence)

    # Check exact math
    assert features.home_last5_ppg == 2.0
    assert features.home_last5_goals_for_per_match == 1.6
    assert features.home_last5_goals_against_per_match == 1.0

    assert features.home_last10_ppg == 2.0
    assert features.home_last10_goals_for_per_match == 1.6
    assert features.home_last10_goals_against_per_match == 0.9
    assert features.home_scored_rate == 0.8
    assert features.home_conceded_rate == 0.6
    assert features.home_clean_sheet_rate == 0.4
    assert features.home_home_split_ppg == 2.6667
    assert features.home_sample_size == 10

    # Schedule: most recent match was 3 days ago
    assert features.home_days_since_last_match == 3.0
    # Matches in last 7 days: 3d and 6d ago -> 2 matches
    assert features.home_matches_last_7d == 2
    # Matches in last 14 days: 3d, 6d, 10d, 13d ago -> 4 matches
    assert features.home_matches_last_14d == 4


def test_missing_features_are_strictly_none_not_zero() -> None:
    kickoff = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
    fix_info = _fixture_info(kickoff)

    evidence = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=kickoff - timedelta(hours=5),
        fixture=fix_info,
        standings=None,
        home_team_stats=None,
        away_team_stats=None,
        home_form=None,
        away_form=None,
        home_availability=None,
        away_availability=None,
        home_lineup=None,
        away_lineup=None,
        odds_set=None,
    )

    features = build_features(evidence)

    # Form metrics must be None, NOT 0.0
    assert features.home_last5_ppg is None
    assert features.away_last5_ppg is None
    assert features.home_last10_ppg is None
    assert features.away_last10_ppg is None
    assert features.home_last10_goals_for_per_match is None
    assert features.home_scored_rate is None
    assert features.home_clean_sheet_rate is None
    assert features.home_home_split_ppg is None

    # Schedule metrics must be None, NOT 0.0
    assert features.home_days_since_last_match is None
    assert features.rest_days_delta is None
    assert features.fixture_congestion_delta is None

    # Standings metrics must be None, NOT 0
    assert features.home_league_position is None
    assert features.league_position_delta is None
    assert features.home_season_points_per_game is None

    # Odds metrics must be None, NOT 0.0
    assert features.market_home_no_vig is None
    assert features.market_draw_no_vig is None
    assert features.market_away_no_vig is None
    assert features.odds_move_home is None

    # Missing reasons must be documented
    assert "home_form" in features.missing_features
    assert "away_form" in features.missing_features
    assert "standings" in features.missing_features
    assert "odds" in features.missing_features


def test_standings_and_market_odds_and_movement_features() -> None:
    kickoff = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
    fix_info = _fixture_info(kickoff)

    # Standings snapshot: Arsenal (rank 2, played 10, pts 24, gf 22, ga 8)
    # Chelsea (rank 5, played 10, pts 18, gf 17, ga 12)
    standings_rows = [
        {
            "provider_team_id": 42,
            "rank": 2,
            "played": 10,
            "points": 24,
            "goals_for": 22,
            "goals_against": 8,
        },
        {
            "provider_team_id": 49,
            "rank": 5,
            "played": 10,
            "points": 18,
            "goals_for": 17,
            "goals_against": 12,
        },
    ]

    standings = StandingSnapshot(
        provider="api_football",
        league_id=fix_info.league_id,
        season_id=fix_info.season_id,
        captured_at=kickoff - timedelta(hours=6),
        source_fingerprint="fp-standings",
        rows_jsonb=standings_rows,
    )

    # Odds set
    odds_set_id = uuid.uuid4()
    odds_set = OddsSnapshotSet(
        id=odds_set_id,
        fixture_id=fix_info.fixture_id,
        provider="theoddsapi",
        captured_at=kickoff - timedelta(hours=2),
        market_whitelist_jsonb=["h2h_1x2", "ou_25", "btts"],
    )

    odds_prices = [
        OddsPrice(
            snapshot_set_id=odds_set_id,
            bookmaker="bet365",
            market="h2h_1x2",
            selection="home",
            decimal_odds=Decimal("2.10"),
            implied_probability=Decimal("0.476190"),
            no_vig_probability=Decimal("0.450000"),
        ),
        OddsPrice(
            snapshot_set_id=odds_set_id,
            bookmaker="bet365",
            market="h2h_1x2",
            selection="draw",
            decimal_odds=Decimal("3.40"),
            implied_probability=Decimal("0.294118"),
            no_vig_probability=Decimal("0.280000"),
        ),
        OddsPrice(
            snapshot_set_id=odds_set_id,
            bookmaker="bet365",
            market="h2h_1x2",
            selection="away",
            decimal_odds=Decimal("3.70"),
            implied_probability=Decimal("0.270270"),
            no_vig_probability=Decimal("0.270000"),
        ),
        OddsPrice(
            snapshot_set_id=odds_set_id,
            bookmaker="bet365",
            market="ou_25",
            selection="over",
            decimal_odds=Decimal("1.85"),
            implied_probability=Decimal("0.540541"),
            no_vig_probability=Decimal("0.520000"),
        ),
        OddsPrice(
            snapshot_set_id=odds_set_id,
            bookmaker="bet365",
            market="ou_25",
            selection="under",
            decimal_odds=Decimal("2.00"),
            implied_probability=Decimal("0.500000"),
            no_vig_probability=Decimal("0.480000"),
        ),
        OddsPrice(
            snapshot_set_id=odds_set_id,
            bookmaker="bet365",
            market="btts",
            selection="yes",
            decimal_odds=Decimal("1.75"),
            implied_probability=Decimal("0.571429"),
            no_vig_probability=Decimal("0.550000"),
        ),
        OddsPrice(
            snapshot_set_id=odds_set_id,
            bookmaker="bet365",
            market="btts",
            selection="no",
            decimal_odds=Decimal("2.15"),
            implied_probability=Decimal("0.465116"),
            no_vig_probability=Decimal("0.450000"),
        ),
    ]

    # Earlier odds set for movement comparison (e.g. 5 hours earlier)
    prev_set_id = uuid.uuid4()
    prev_set = OddsSnapshotSet(
        id=prev_set_id,
        fixture_id=fix_info.fixture_id,
        provider="theoddsapi",
        captured_at=kickoff - timedelta(hours=7),
        market_whitelist_jsonb=["h2h_1x2", "ou_25"],
    )
    prev_prices = [
        OddsPrice(
            snapshot_set_id=prev_set_id,
            bookmaker="bet365",
            market="h2h_1x2",
            selection="home",
            decimal_odds=Decimal("2.25"),  # Home odds dropped from 2.25 to 2.10 (-0.15)
            implied_probability=Decimal("0.444444"),
            no_vig_probability=Decimal("0.420000"),
        ),
        OddsPrice(
            snapshot_set_id=prev_set_id,
            bookmaker="bet365",
            market="ou_25",
            selection="over",
            decimal_odds=Decimal("1.80"),  # Over 2.5 drifted from 1.80 to 1.85 (+0.05)
            implied_probability=Decimal("0.555556"),
            no_vig_probability=Decimal("0.530000"),
        ),
    ]

    # Availability snapshot
    home_avail = AvailabilitySnapshot(
        provider="api_football",
        fixture_id=fix_info.fixture_id,
        team_id=fix_info.home_team_id,
        captured_at=kickoff - timedelta(hours=3),
        availability_state="KNOWN_PRESENT",
        players_jsonb=[
            {"player_name": "Player A", "missing": True},
            {"player_name": "Player B", "missing": False},
        ],
        impact_flags_jsonb=[],
        conflicts_jsonb=[],
    )

    evidence = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.PREMATCH,
        as_of=kickoff - timedelta(hours=1),
        fixture=fix_info,
        standings=standings,
        home_team_stats=None,
        away_team_stats=None,
        home_form=None,
        away_form=None,
        home_availability=home_avail,
        away_availability=None,
        home_lineup=None,
        away_lineup=None,
        odds_set=odds_set,
        odds_prices=odds_prices,
        prev_odds_set=prev_set,
        prev_odds_prices=prev_prices,
    )

    features = build_features(evidence)

    # Standings math
    assert features.home_league_position == 2
    assert features.away_league_position == 5
    assert features.league_position_delta == -3
    assert features.home_season_points_per_game == 2.4
    assert features.away_season_points_per_game == 1.8
    assert features.home_season_goals_for_per_game == 2.2
    assert features.home_season_goals_against_per_game == 0.8

    # Market math
    assert features.market_home_no_vig == 0.45
    assert features.market_draw_no_vig == 0.28
    assert features.market_away_no_vig == 0.27
    assert features.market_over25_no_vig == 0.52
    assert features.market_btts_yes_no_vig == 0.55

    # Odds movement math
    # 2.10 - 2.25 = -0.15
    assert features.odds_move_home == -0.15
    # 1.85 - 1.80 = 0.05
    assert features.odds_move_over25 == 0.05

    # Availability
    assert features.home_missing_players_count == 1
    assert features.home_availability_state == "KNOWN_PRESENT"


def test_form_math_missing_goals_not_zero_or_fake_clean_sheet() -> None:
    kickoff = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
    fix_info = _fixture_info(kickoff)

    # 3 outcomes:
    # Outcome 0: W, gf=2, ga=None -> missing GA must NOT count as clean sheet!
    # Outcome 1: L, gf=None, ga=3 -> missing GF must NOT count as failed to score!
    # Outcome 2: D, gf=1, ga=1
    home_outcomes = [
        {
            "outcome": "W",
            "result": "W",
            "goals_for": 2,
            "goals_against": None,
            "is_home": True,
            "kickoff_utc": (kickoff - timedelta(days=3)).isoformat(),
        },
        {
            "outcome": "L",
            "result": "L",
            "goals_for": None,
            "goals_against": 3,
            "is_home": False,
            "kickoff_utc": (kickoff - timedelta(days=7)).isoformat(),
        },
        {
            "outcome": "D",
            "result": "D",
            "goals_for": 1,
            "goals_against": 1,
            "is_home": True,
            "kickoff_utc": (kickoff - timedelta(days=12)).isoformat(),
        },
    ]
    home_form = TeamFormSnapshot(
        team_id=fix_info.home_team_id,
        as_of=kickoff - timedelta(hours=5),
        window_size=10,
        scope="overall",
        metrics_jsonb={"outcomes": home_outcomes, "window_size": 10},
        source_fingerprint="fp-home-form",
    )
    evidence = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=kickoff - timedelta(hours=5),
        fixture=fix_info,
        standings=None,
        home_team_stats=None,
        away_team_stats=None,
        home_form=home_form,
        away_form=None,
        home_availability=None,
        away_availability=None,
        home_lineup=None,
        away_lineup=None,
        odds_set=None,
    )
    features = build_features(evidence)
    # Valid GF samples = 2 (matches 0 and 2: gf 2 + 1 = 3 / 2 = 1.5)
    assert features.home_last10_goals_for_per_match == 1.5
    # Valid GA samples = 2 (matches 1 and 2: ga 3 + 1 = 4 / 2 = 2.0)
    assert features.home_last10_goals_against_per_match == 2.0
    # Clean sheet count: match 0 has ga=None -> NOT clean sheet.
    # match 1 has ga=3 -> not. match 2 has ga=1 -> not. Total CS = 0!
    assert features.home_clean_sheet_rate == 0.0
    # Scored in 2 matches out of 2 valid GF matches = 1.0
    assert features.home_scored_rate == 1.0
    assert features.home_conceded_rate == 1.0


def test_multi_bookmaker_insertion_order_determinism() -> None:
    from itertools import permutations

    kickoff = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
    fix_info = _fixture_info(kickoff)

    set_id = uuid.uuid4()
    odds_set = OddsSnapshotSet(
        id=set_id,
        fixture_id=fix_info.fixture_id,
        provider="theoddsapi",
        captured_at=kickoff - timedelta(hours=2),
        market_whitelist_jsonb=["h2h_1x2"],
    )
    # 3 bookmakers: Bet365 (home=2.10, no_vig=0.45),
    # Pinnacle (home=2.15, no_vig=0.46), Unibet (home=2.05, no_vig=0.44)
    # Median home no_vig = 0.45.
    p1 = OddsPrice(
        snapshot_set_id=set_id,
        bookmaker="bet365",
        market="h2h_1x2",
        selection="home",
        decimal_odds=Decimal("2.10"),
        implied_probability=Decimal("0.476190"),
        no_vig_probability=Decimal("0.450000"),
    )
    p2 = OddsPrice(
        snapshot_set_id=set_id,
        bookmaker="pinnacle",
        market="h2h_1x2",
        selection="home",
        decimal_odds=Decimal("2.15"),
        implied_probability=Decimal("0.465116"),
        no_vig_probability=Decimal("0.460000"),
    )
    p3 = OddsPrice(
        snapshot_set_id=set_id,
        bookmaker="unibet",
        market="h2h_1x2",
        selection="home",
        decimal_odds=Decimal("2.05"),
        implied_probability=Decimal("0.487805"),
        no_vig_probability=Decimal("0.440000"),
    )

    results = []
    for perm in permutations([p1, p2, p3]):
        evidence = SelectedEvidence(
            fixture_id=fix_info.fixture_id,
            forecast_phase=ForecastPhase.PREMATCH,
            as_of=kickoff - timedelta(hours=1),
            fixture=fix_info,
            standings=None,
            home_team_stats=None,
            away_team_stats=None,
            home_form=None,
            away_form=None,
            home_availability=None,
            away_availability=None,
            home_lineup=None,
            away_lineup=None,
            odds_set=odds_set,
            odds_prices=list(perm),
        )
        feats = build_features(evidence)
        results.append(feats.market_home_no_vig)

    # All permutations produce identical median consensus
    for res in results:
        assert res == 0.45


def test_provider_scoped_team_identity() -> None:
    kickoff = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
    fix_id = uuid.uuid4()
    h_id = uuid.uuid4()
    a_id = uuid.uuid4()

    # Home team has two external IDs: mock -> "999", api_football -> "42"
    # Away team has two external IDs: mock -> "888", api_football -> "49"
    fix_info = SelectedFixtureInfo(
        fixture_id=fix_id,
        league_id=uuid.uuid4(),
        season_id=uuid.uuid4(),
        home_team_id=h_id,
        away_team_id=a_id,
        kickoff_at=kickoff,
        venue="Emirates Stadium",
        round="Regular Season - 1",
        status="NS",
        league_slug="premier-league",
        league_name="Premier League",
        home_team_name="Arsenal",
        away_team_name="Chelsea",
        home_provider_mappings=[],
        away_provider_mappings=[],
        home_provider_external_ids={"mock": "999", "api_football": "42"},
        away_provider_external_ids={"mock": "888", "api_football": "49"},
    )

    # Standings snapshot is from "api_football"
    standings = StandingSnapshot(
        provider="api_football",
        league_id=fix_info.league_id,
        season_id=fix_info.season_id,
        captured_at=kickoff - timedelta(hours=6),
        source_fingerprint="fp-st",
        rows_jsonb=[
            {
                "provider_team_id": 42,
                "rank": 1,
                "played": 10,
                "points": 25,
                "goals_for": 22,
                "goals_against": 8,
            },
            {
                "provider_team_id": 49,
                "rank": 4,
                "played": 10,
                "points": 18,
                "goals_for": 16,
                "goals_against": 12,
            },
            {
                "provider_team_id": 999,
                "rank": 20,
                "played": 10,
                "points": 2,
                "goals_for": 3,
                "goals_against": 25,
            },
        ],
    )

    evidence = SelectedEvidence(
        fixture_id=fix_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=kickoff - timedelta(hours=5),
        fixture=fix_info,
        standings=standings,
        home_team_stats=None,
        away_team_stats=None,
        home_form=None,
        away_form=None,
        home_availability=None,
        away_availability=None,
        home_lineup=None,
        away_lineup=None,
        odds_set=None,
    )

    features = build_features(evidence)
    # Must resolve to rank 1 (from api_football team_id 42), NOT rank 20 (from mock team_id 999)
    assert features.home_league_position == 1
    assert features.away_league_position == 4
