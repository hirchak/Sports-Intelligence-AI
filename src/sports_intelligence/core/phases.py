from __future__ import annotations

from enum import StrEnum


class ForecastPhase(StrEnum):
    MORNING = "MORNING"
    PREMATCH = "PREMATCH"
    POSTMATCH = "POSTMATCH"


class FreshnessCategory(StrEnum):
    LEAGUE_METADATA = "league_metadata"
    TEAM_METADATA = "team_metadata"
    STANDINGS = "standings"
    TEAM_STATISTICS = "team_statistics"
    TEAM_FORM = "team_form"
    AVAILABILITY = "availability"
    LINEUPS = "lineups"
    ODDS = "odds"
    RESEARCH = "research"


class Priority(StrEnum):
    P0 = "P0"  # settlement / critical pre-kickoff / manual
    P1 = "P1"  # pre-kickoff availability, pre-kickoff odds, lineups
    P2 = "P2"  # standings, team stats, form inputs
    P3 = "P3"  # optional / experimental collectors / research


class DegradationMode(StrEnum):
    NORMAL = "NORMAL"
    CONSERVE = "CONSERVE"
    CRITICAL = "CRITICAL"
    RESERVE_ONLY = "RESERVE_ONLY"


class AvailabilityState(StrEnum):
    KNOWN_NONE = "KNOWN_NONE"  # provider confirmed no injuries
    KNOWN_PRESENT = "KNOWN_PRESENT"  # provider returned concrete availability list
    UNKNOWN = "UNKNOWN"  # provider silent or absent (spec 14 §7)
    STALE = "STALE"  # snapshot older than freshness threshold
    CONFLICTED = "CONFLICTED"  # multiple sources disagree


class ResearchState(StrEnum):
    AVAILABLE = "AVAILABLE"
    NO_USEFUL_RESULTS = "NO_USEFUL_RESULTS"
    DISABLED = "DISABLED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    STALE = "STALE"
    EXTRACTION_UNAVAILABLE = "EXTRACTION_UNAVAILABLE"


class ClaimType(StrEnum):
    AVAILABILITY = "availability"
    SUSPENSION = "suspension"
    ROTATION = "rotation"
    LINEUP = "lineup"
    MANAGER_STATEMENT = "manager_statement"
    TACTICAL = "tactical"
    SCHEDULE_CONGESTION = "schedule_congestion"
    TRAVEL = "travel"
    TEAM_NEWS = "team_news"
    OTHER = "other"
