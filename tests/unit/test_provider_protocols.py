from __future__ import annotations

from sports_intelligence.providers.base import LLMProvider, SportsDataProvider


def _public_member_names(protocol: type) -> set[str]:
    return {name for name in dir(protocol) if not name.startswith("_")}


def test_sports_provider_interface_declares_typed_discovery_surface() -> None:
    member_names = _public_member_names(SportsDataProvider)
    assert {"get_fixtures_by_date", "capabilities"}.issubset(member_names)


def test_sports_provider_interface_no_longer_exposes_untyped_dict_methods() -> None:
    member_names = _public_member_names(SportsDataProvider)
    # Untyped dict-returning legacy methods must never be part of the
    # surface.
    for legacy_method in (
        "get_fixtures",
        "get_fixture",
        "get_team_recent_matches",
        "get_head_to_head",
        "get_injuries",
        "get_result",
    ):
        assert legacy_method not in member_names


def test_sports_provider_interface_declares_typed_m4_category_methods() -> None:
    member_names = _public_member_names(SportsDataProvider)
    assert {
        "get_standings",
        "get_team_statistics",
        "get_availability",
        "get_lineups",
        "get_completed_fixtures",
    }.issubset(member_names)


def test_llm_provider_interface_declares_structured_generation() -> None:
    member_names = _public_member_names(LLMProvider)
    assert "generate_structured" in member_names
