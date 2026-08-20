from __future__ import annotations

from sports_intelligence.providers.base import LLMProvider, SportsDataProvider

REQUIRED_SPORTS_METHODS = {
    "get_fixtures",
    "get_fixture",
    "get_standings",
    "get_team_recent_matches",
    "get_head_to_head",
    "get_injuries",
    "get_lineups",
    "get_team_statistics",
    "get_result",
}


def _public_member_names(protocol: type) -> set[str]:
    return {name for name in dir(protocol) if not name.startswith("_")}


def test_sports_provider_interface_declares_minimum_methods() -> None:
    assert REQUIRED_SPORTS_METHODS.issubset(_public_member_names(SportsDataProvider))


def test_llm_provider_interface_declares_structured_generation() -> None:
    assert "generate_structured" in _public_member_names(LLMProvider)
