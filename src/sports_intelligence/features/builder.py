from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sports_intelligence.context.selector import SelectedEvidence


@dataclass(frozen=True)
class DeterministicFeatures:
    schema_version: str = "features_v1"

    # Form (Last 5 & Last 10)
    home_last5_ppg: float | None = None
    away_last5_ppg: float | None = None
    home_last10_ppg: float | None = None
    away_last10_ppg: float | None = None
    home_last10_goals_for_per_match: float | None = None
    away_last10_goals_for_per_match: float | None = None
    home_last10_goals_against_per_match: float | None = None
    away_last10_goals_against_per_match: float | None = None
    home_last5_goals_for_per_match: float | None = None
    away_last5_goals_for_per_match: float | None = None
    home_last5_goals_against_per_match: float | None = None
    away_last5_goals_against_per_match: float | None = None
    home_home_split_ppg: float | None = None
    away_away_split_ppg: float | None = None
    home_scored_rate: float | None = None
    away_scored_rate: float | None = None
    home_conceded_rate: float | None = None
    away_conceded_rate: float | None = None
    home_clean_sheet_rate: float | None = None
    away_clean_sheet_rate: float | None = None
    home_sample_size: int | None = None
    away_sample_size: int | None = None

    # Schedule / Fatigue
    home_days_since_last_match: float | None = None
    away_days_since_last_match: float | None = None
    rest_days_delta: float | None = None
    home_matches_last_7d: int | None = None
    away_matches_last_7d: int | None = None
    home_matches_last_14d: int | None = None
    away_matches_last_14d: int | None = None
    fixture_congestion_delta: int | None = None

    # Standings / Season Strength
    home_league_position: int | None = None
    away_league_position: int | None = None
    league_position_delta: int | None = None
    home_season_points_per_game: float | None = None
    away_season_points_per_game: float | None = None
    home_season_goals_for_per_game: float | None = None
    away_season_goals_for_per_game: float | None = None
    home_season_goals_against_per_game: float | None = None
    away_season_goals_against_per_game: float | None = None

    # Availability
    home_missing_players_count: int | None = None
    away_missing_players_count: int | None = None
    home_availability_state: str | None = None
    away_availability_state: str | None = None
    home_availability_conflict_count: int | None = None
    away_availability_conflict_count: int | None = None
    important_absence_delta: float | None = None
    top_scorer_missing: bool | None = None
    starting_goalkeeper_missing: bool | None = None
    multiple_starting_defenders_missing: bool | None = None

    # Lineups
    home_lineup_confirmed: bool | None = None
    away_lineup_confirmed: bool | None = None
    lineups_both_confirmed: bool | None = None
    home_lineup_formation: str | None = None
    away_lineup_formation: str | None = None
    home_lineup_publication_state: str | None = None
    away_lineup_publication_state: str | None = None

    # Market (No-vig)
    market_home_no_vig: float | None = None
    market_draw_no_vig: float | None = None
    market_away_no_vig: float | None = None
    market_over15_no_vig: float | None = None
    market_under15_no_vig: float | None = None
    market_over25_no_vig: float | None = None
    market_under25_no_vig: float | None = None
    market_btts_yes_no_vig: float | None = None
    market_btts_no_no_vig: float | None = None

    # Odds Movement
    odds_move_home: float | None = None
    odds_move_over25: float | None = None

    # Diagnostics
    missing_features: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_iso_utc(dt_str: str) -> datetime:
    dt = datetime.fromisoformat(dt_str)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _calc_form_metrics(
    outcomes: list[dict[str, Any]],
    n: int,
) -> tuple[float | None, float | None, float | None, float | None, float | None, float | None]:
    """Calculate (ppg, gf_per_match, ga_per_match, scored_rate, conceded_rate, clean_sheet_rate).

    Missing data returns None — never converts missing into 0.0.
    """
    sample = outcomes[:n]
    if not sample:
        return None, None, None, None, None, None

    points = 0
    points_valid_count = 0

    gf_total = 0
    gf_valid_count = 0
    scored_count = 0

    ga_total = 0
    ga_valid_count = 0
    conceded_count = 0
    clean_sheets = 0

    for m in sample:
        outcome = m.get("outcome") or m.get("result")
        if outcome in ("W", "D", "L"):
            points_valid_count += 1
            if outcome == "W":
                points += 3
            elif outcome == "D":
                points += 1

        raw_gf = m.get("goals_for")
        if raw_gf is not None:
            try:
                gf = int(raw_gf)
                gf_total += gf
                gf_valid_count += 1
                if gf > 0:
                    scored_count += 1
            except (ValueError, TypeError):
                pass

        raw_ga = m.get("goals_against")
        if raw_ga is not None:
            try:
                ga = int(raw_ga)
                ga_total += ga
                ga_valid_count += 1
                if ga > 0:
                    conceded_count += 1
                elif ga == 0:
                    clean_sheets += 1
            except (ValueError, TypeError):
                pass

    ppg = round(points / points_valid_count, 4) if points_valid_count > 0 else None
    gf_pm = round(gf_total / gf_valid_count, 4) if gf_valid_count > 0 else None
    ga_pm = round(ga_total / ga_valid_count, 4) if ga_valid_count > 0 else None
    sc_rate = round(scored_count / gf_valid_count, 4) if gf_valid_count > 0 else None
    cc_rate = round(conceded_count / ga_valid_count, 4) if ga_valid_count > 0 else None
    cs_rate = round(clean_sheets / ga_valid_count, 4) if ga_valid_count > 0 else None

    return ppg, gf_pm, ga_pm, sc_rate, cc_rate, cs_rate


def _calc_split_ppg(outcomes: list[dict[str, Any]], *, target_home: bool) -> float | None:
    """Calculate PPG specifically for home matches (target_home=True) or away matches."""
    matching = [m for m in outcomes if m.get("is_home") is target_home]
    if not matching:
        return None
    points = 0
    for m in matching:
        outcome = m.get("outcome") or m.get("result")
        if outcome == "W":
            points += 3
        elif outcome == "D":
            points += 1
    return round(points / len(matching), 4)


def _calc_schedule(
    outcomes: list[dict[str, Any]],
    kickoff_at: datetime,
) -> tuple[float | None, int | None, int | None]:
    """Calculate (days_since_last_match, matches_last_7d, matches_last_14d)."""
    if not outcomes:
        return None, None, None

    kickoff_utc = kickoff_at if kickoff_at.tzinfo else kickoff_at.replace(tzinfo=UTC)
    dates: list[datetime] = []
    for m in outcomes:
        k_str = m.get("kickoff_utc")
        if k_str:
            try:
                dates.append(_parse_iso_utc(k_str))
            except Exception:
                continue

    if not dates:
        return None, None, None

    # Filter matches prior to current kickoff
    prior_dates = [d for d in dates if d < kickoff_utc]
    if not prior_dates:
        return None, None, None

    most_recent = max(prior_dates)
    days_since = round((kickoff_utc - most_recent).total_seconds() / 86400.0, 2)

    cutoff_7d = kickoff_utc - timedelta(days=7)
    cutoff_14d = kickoff_utc - timedelta(days=14)

    m_7d = sum(1 for d in prior_dates if cutoff_7d <= d)
    m_14d = sum(1 for d in prior_dates if cutoff_14d <= d)

    return days_since, m_7d, m_14d


def _median_no_vig(prices: list[Any], market: str, selection: str) -> float | None:
    vals = [
        float(p.no_vig_probability)
        for p in prices
        if getattr(p, "market", None) == market
        and getattr(p, "selection", None) == selection
        and getattr(p, "no_vig_probability", None) is not None
    ]
    if not vals:
        return None
    return round(float(statistics.median(vals)), 4)


def _median_decimal_odds(prices: list[Any], market: str, selection: str) -> float | None:
    vals = [
        float(p.decimal_odds)
        for p in prices
        if getattr(p, "market", None) == market
        and getattr(p, "selection", None) == selection
        and getattr(p, "decimal_odds", None) is not None
    ]
    if not vals:
        return None
    return round(float(statistics.median(vals)), 4)


def build_features(evidence: SelectedEvidence) -> DeterministicFeatures:
    """Pure deterministic calculation of Features V1 from selected point-in-time evidence.

    Zero external API calls.
    Missing evidence produces None (NEVER fake zeroes).
    All missing features are tracked with explicit reasons in missing_features.
    """
    missing: dict[str, str] = {}

    # 1. Form & Schedule
    home_form_outcomes: list[dict[str, Any]] = []
    if evidence.home_form and isinstance(evidence.home_form.metrics_jsonb, dict):
        home_form_outcomes = evidence.home_form.metrics_jsonb.get("outcomes", [])
    else:
        missing["home_form"] = "No home team form snapshot available <= as_of"

    away_form_outcomes: list[dict[str, Any]] = []
    if evidence.away_form and isinstance(evidence.away_form.metrics_jsonb, dict):
        away_form_outcomes = evidence.away_form.metrics_jsonb.get("outcomes", [])
    else:
        missing["away_form"] = "No away team form snapshot available <= as_of"

    home_sample_size = len(home_form_outcomes) if home_form_outcomes else None
    away_sample_size = len(away_form_outcomes) if away_form_outcomes else None

    # Last 5
    h_l5_ppg, h_l5_gf, h_l5_ga, _, _, _ = _calc_form_metrics(home_form_outcomes, 5)
    a_l5_ppg, a_l5_gf, a_l5_ga, _, _, _ = _calc_form_metrics(away_form_outcomes, 5)

    # Last 10
    h_l10_ppg, h_l10_gf, h_l10_ga, h_sc_rate, h_cc_rate, h_cs_rate = _calc_form_metrics(
        home_form_outcomes, 10
    )
    a_l10_ppg, a_l10_gf, a_l10_ga, a_sc_rate, a_cc_rate, a_cs_rate = _calc_form_metrics(
        away_form_outcomes, 10
    )

    # Splits
    home_home_split = _calc_split_ppg(home_form_outcomes, target_home=True)
    away_away_split = _calc_split_ppg(away_form_outcomes, target_home=False)

    # Schedule
    h_days, h_7d, h_14d = _calc_schedule(home_form_outcomes, evidence.fixture.kickoff_at)
    a_days, a_days_7d, a_days_14d = _calc_schedule(away_form_outcomes, evidence.fixture.kickoff_at)

    rest_days_delta = (
        round(h_days - a_days, 2) if (h_days is not None and a_days is not None) else None
    )
    congestion_delta = (
        (h_14d - a_days_14d) if (h_14d is not None and a_days_14d is not None) else None
    )

    # 2. Standings & Season Strength
    home_pos: int | None = None
    away_pos: int | None = None
    h_season_ppg: float | None = None
    a_season_ppg: float | None = None
    h_season_gf_pm: float | None = None
    a_season_gf_pm: float | None = None
    h_season_ga_pm: float | None = None
    a_season_ga_pm: float | None = None

    if evidence.standings and isinstance(evidence.standings.rows_jsonb, list):
        standings_prov = evidence.standings.provider
        home_ext = evidence.fixture.get_home_external_id(standings_prov)
        away_ext = evidence.fixture.get_away_external_id(standings_prov)

        for row in evidence.standings.rows_jsonb:
            if not isinstance(row, dict):
                continue
            prov_id = str(row.get("provider_team_id"))
            team_name = row.get("team_name")

            is_home_match = (home_ext is not None and prov_id == str(home_ext)) or (
                team_name and team_name == evidence.fixture.home_team_name
            )
            is_away_match = (away_ext is not None and prov_id == str(away_ext)) or (
                team_name and team_name == evidence.fixture.away_team_name
            )

            rank = row.get("rank")
            played = row.get("played")
            points = row.get("points")
            gf = row.get("goals_for")
            ga = row.get("goals_against")

            if is_home_match and home_pos is None:
                home_pos = int(rank) if rank is not None else None
                if played and int(played) > 0:
                    p_cnt = int(played)
                    h_season_ppg = round(int(points) / p_cnt, 4) if points is not None else None
                    h_season_gf_pm = round(int(gf) / p_cnt, 4) if gf is not None else None
                    h_season_ga_pm = round(int(ga) / p_cnt, 4) if ga is not None else None

            if is_away_match and away_pos is None:
                away_pos = int(rank) if rank is not None else None
                if played and int(played) > 0:
                    p_cnt = int(played)
                    a_season_ppg = round(int(points) / p_cnt, 4) if points is not None else None
                    a_season_gf_pm = round(int(gf) / p_cnt, 4) if gf is not None else None
                    a_season_ga_pm = round(int(ga) / p_cnt, 4) if ga is not None else None
    else:
        missing["standings"] = "No standings snapshot available for season <= as_of"

    pos_delta = (home_pos - away_pos) if (home_pos is not None and away_pos is not None) else None

    # 3. Availability
    home_missing_cnt: int | None = None
    home_avail_state: str | None = None
    home_conflicts: int | None = None
    if evidence.home_availability is not None:
        home_avail_state = evidence.home_availability.availability_state
        players = evidence.home_availability.players_jsonb or []
        home_missing_cnt = sum(
            1 for p in players if isinstance(p, dict) and p.get("missing") is True
        )
        home_conflicts = len(evidence.home_availability.conflicts_jsonb or [])
    else:
        home_avail_state = "UNKNOWN"
        missing["home_availability"] = "No home availability snapshot <= as_of"

    away_missing_cnt: int | None = None
    away_avail_state: str | None = None
    away_conflicts: int | None = None
    if evidence.away_availability is not None:
        away_avail_state = evidence.away_availability.availability_state
        players = evidence.away_availability.players_jsonb or []
        away_missing_cnt = sum(
            1 for p in players if isinstance(p, dict) and p.get("missing") is True
        )
        away_conflicts = len(evidence.away_availability.conflicts_jsonb or [])
    else:
        away_avail_state = "UNKNOWN"
        missing["away_availability"] = "No away availability snapshot <= as_of"

    # Explicitly deferred absence impact features
    missing["important_absence_delta"] = "Player role/value impact model deferred beyond V1"
    missing["top_scorer_missing"] = "Top scorer role metadata not available in V1 snapshots"
    missing["starting_goalkeeper_missing"] = (
        "Goalkeeper role metadata not available in V1 snapshots"
    )
    missing["multiple_starting_defenders_missing"] = (
        "Defender role count metadata not available in V1 snapshots"
    )

    # 4. Lineups
    h_lineup_conf: bool | None = None
    a_lineup_conf: bool | None = None
    h_formation: str | None = None
    a_formation: str | None = None
    h_pub_state: str | None = "NOT_YET_PUBLISHED"
    a_pub_state: str | None = "NOT_YET_PUBLISHED"

    if evidence.home_lineup is not None:
        h_lineup_conf = evidence.home_lineup.confirmed
        h_formation = evidence.home_lineup.formation
        h_pub_state = evidence.home_lineup.publication_state
    else:
        missing["home_lineup"] = "No home lineup snapshot <= as_of"

    if evidence.away_lineup is not None:
        a_lineup_conf = evidence.away_lineup.confirmed
        a_formation = evidence.away_lineup.formation
        a_pub_state = evidence.away_lineup.publication_state
    else:
        missing["away_lineup"] = "No away lineup snapshot <= as_of"

    both_confirmed: bool | None = None
    if h_lineup_conf is not None and a_lineup_conf is not None:
        both_confirmed = bool(h_lineup_conf and a_lineup_conf)

    # 5. Market Odds & Movement
    m_home_nv: float | None = None
    m_draw_nv: float | None = None
    m_away_nv: float | None = None
    m_o15_nv: float | None = None
    m_u15_nv: float | None = None
    m_o25_nv: float | None = None
    m_u25_nv: float | None = None
    m_btts_y_nv: float | None = None
    m_btts_n_nv: float | None = None

    if evidence.odds_set and evidence.odds_prices:
        m_home_nv = _median_no_vig(evidence.odds_prices, "h2h_1x2", "home")
        m_draw_nv = _median_no_vig(evidence.odds_prices, "h2h_1x2", "draw")
        m_away_nv = _median_no_vig(evidence.odds_prices, "h2h_1x2", "away")
        m_o15_nv = _median_no_vig(evidence.odds_prices, "ou_15", "over")
        m_u15_nv = _median_no_vig(evidence.odds_prices, "ou_15", "under")
        m_o25_nv = _median_no_vig(evidence.odds_prices, "ou_25", "over")
        m_u25_nv = _median_no_vig(evidence.odds_prices, "ou_25", "under")
        m_btts_y_nv = _median_no_vig(evidence.odds_prices, "btts", "yes")
        m_btts_n_nv = _median_no_vig(evidence.odds_prices, "btts", "no")
    else:
        missing["odds"] = "No odds snapshot set <= as_of"

    # Odds Movement (Consensus Median Movement)
    odds_move_home: float | None = None
    odds_move_over25: float | None = None

    if evidence.odds_prices and evidence.prev_odds_prices:
        cur_home = _median_decimal_odds(evidence.odds_prices, "h2h_1x2", "home")
        prev_home = _median_decimal_odds(evidence.prev_odds_prices, "h2h_1x2", "home")
        if cur_home is not None and prev_home is not None:
            odds_move_home = round(cur_home - prev_home, 4)

        cur_o25 = _median_decimal_odds(evidence.odds_prices, "ou_25", "over")
        prev_o25 = _median_decimal_odds(evidence.prev_odds_prices, "ou_25", "over")
        if cur_o25 is not None and prev_o25 is not None:
            odds_move_over25 = round(cur_o25 - prev_o25, 4)
    else:
        missing["odds_movement"] = (
            "No prior odds snapshot available <= as_of for movement comparison"
        )

    return DeterministicFeatures(
        schema_version="features_v1",
        home_last5_ppg=h_l5_ppg,
        away_last5_ppg=a_l5_ppg,
        home_last10_ppg=h_l10_ppg,
        away_last10_ppg=a_l10_ppg,
        home_last10_goals_for_per_match=h_l10_gf,
        away_last10_goals_for_per_match=a_l10_gf,
        home_last10_goals_against_per_match=h_l10_ga,
        away_last10_goals_against_per_match=a_l10_ga,
        home_last5_goals_for_per_match=h_l5_gf,
        away_last5_goals_for_per_match=a_l5_gf,
        home_last5_goals_against_per_match=h_l5_ga,
        away_last5_goals_against_per_match=a_l5_ga,
        home_home_split_ppg=home_home_split,
        away_away_split_ppg=away_away_split,
        home_scored_rate=h_sc_rate,
        away_scored_rate=a_sc_rate,
        home_conceded_rate=h_cc_rate,
        away_conceded_rate=a_cc_rate,
        home_clean_sheet_rate=h_cs_rate,
        away_clean_sheet_rate=a_cs_rate,
        home_sample_size=home_sample_size,
        away_sample_size=away_sample_size,
        home_days_since_last_match=h_days,
        away_days_since_last_match=a_days,
        rest_days_delta=rest_days_delta,
        home_matches_last_7d=h_7d,
        away_matches_last_7d=a_days_7d,
        home_matches_last_14d=h_14d,
        away_matches_last_14d=a_days_14d,
        fixture_congestion_delta=congestion_delta,
        home_league_position=home_pos,
        away_league_position=away_pos,
        league_position_delta=pos_delta,
        home_season_points_per_game=h_season_ppg,
        away_season_points_per_game=a_season_ppg,
        home_season_goals_for_per_game=h_season_gf_pm,
        away_season_goals_for_per_game=a_season_gf_pm,
        home_season_goals_against_per_game=h_season_ga_pm,
        away_season_goals_against_per_game=a_season_ga_pm,
        home_missing_players_count=home_missing_cnt,
        away_missing_players_count=away_missing_cnt,
        home_availability_state=home_avail_state,
        away_availability_state=away_avail_state,
        home_availability_conflict_count=home_conflicts,
        away_availability_conflict_count=away_conflicts,
        important_absence_delta=None,
        top_scorer_missing=None,
        starting_goalkeeper_missing=None,
        multiple_starting_defenders_missing=None,
        home_lineup_confirmed=h_lineup_conf,
        away_lineup_confirmed=a_lineup_conf,
        lineups_both_confirmed=both_confirmed,
        home_lineup_formation=h_formation,
        away_lineup_formation=a_formation,
        home_lineup_publication_state=h_pub_state,
        away_lineup_publication_state=a_pub_state,
        market_home_no_vig=m_home_nv,
        market_draw_no_vig=m_draw_nv,
        market_away_no_vig=m_away_nv,
        market_over15_no_vig=m_o15_nv,
        market_under15_no_vig=m_u15_nv,
        market_over25_no_vig=m_o25_nv,
        market_under25_no_vig=m_u25_nv,
        market_btts_yes_no_vig=m_btts_y_nv,
        market_btts_no_no_vig=m_btts_n_nv,
        odds_move_home=odds_move_home,
        odds_move_over25=odds_move_over25,
        missing_features=missing,
    )
