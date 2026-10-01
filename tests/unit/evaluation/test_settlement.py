from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sports_intelligence.evaluation.settlement import (
    Outcome,
    ResultObservation,
    ResultStatus,
    fixed_return,
    settle,
)
from sports_intelligence.predictions.contracts import Selection

# Explicit independent winner sets for each score; all 12 selections tested for every row.
CASES = [
    (0, 0, "DRAW HOME_OR_DRAW DRAW_OR_AWAY UNDER_1_5 UNDER_2_5 BTTS_NO"),
    (1, 0, "HOME HOME_OR_DRAW HOME_OR_AWAY UNDER_1_5 UNDER_2_5 BTTS_NO"),
    (0, 1, "AWAY HOME_OR_AWAY DRAW_OR_AWAY UNDER_1_5 UNDER_2_5 BTTS_NO"),
    (1, 1, "DRAW HOME_OR_DRAW DRAW_OR_AWAY OVER_1_5 UNDER_2_5 BTTS_YES"),
    (2, 0, "HOME HOME_OR_DRAW HOME_OR_AWAY OVER_1_5 UNDER_2_5 BTTS_NO"),
    (0, 2, "AWAY HOME_OR_AWAY DRAW_OR_AWAY OVER_1_5 UNDER_2_5 BTTS_NO"),
    (2, 1, "HOME HOME_OR_DRAW HOME_OR_AWAY OVER_1_5 OVER_2_5 BTTS_YES"),
    (1, 2, "AWAY HOME_OR_AWAY DRAW_OR_AWAY OVER_1_5 OVER_2_5 BTTS_YES"),
    (2, 2, "DRAW HOME_OR_DRAW DRAW_OR_AWAY OVER_1_5 OVER_2_5 BTTS_YES"),
    (3, 0, "HOME HOME_OR_DRAW HOME_OR_AWAY OVER_1_5 OVER_2_5 BTTS_NO"),
    (0, 3, "AWAY HOME_OR_AWAY DRAW_OR_AWAY OVER_1_5 OVER_2_5 BTTS_NO"),
]


def observation(**kwargs):
    return ResultObservation(
        provider_fixture_id=42,
        observed_at=datetime.now(UTC),
        provider_status="FT",
        status=ResultStatus.FINAL,
        **kwargs,
    )


@pytest.mark.parametrize("h,a,winners", CASES)
@pytest.mark.parametrize("selection", list(Selection))
def test_exact_matrix(h, a, winners, selection):
    result = observation(regulation_home=h, regulation_away=a)
    assert settle(selection, result) == (
        Outcome.WIN if selection.value in winners.split() else Outcome.LOSS
    )


@pytest.mark.parametrize("h,a,_", CASES)
def test_complement_and_double_chance_invariants(h, a, _):
    result = observation(regulation_home=h, regulation_away=a)
    won = {s for s in Selection if settle(s, result) == Outcome.WIN}
    assert len(won & {Selection.HOME, Selection.DRAW, Selection.AWAY}) == 1
    for x, y in (
        (Selection.OVER_1_5, Selection.UNDER_1_5),
        (Selection.OVER_2_5, Selection.UNDER_2_5),
        (Selection.BTTS_YES, Selection.BTTS_NO),
    ):
        assert len(won & {x, y}) == 1
    assert (Selection.HOME_OR_DRAW in won) == bool(won & {Selection.HOME, Selection.DRAW})
    assert (Selection.HOME_OR_AWAY in won) == bool(won & {Selection.HOME, Selection.AWAY})
    assert (Selection.DRAW_OR_AWAY in won) == bool(won & {Selection.DRAW, Selection.AWAY})
    assert all(settle(s, result) != Outcome.PUSH for s in Selection)


@pytest.mark.parametrize(
    "status,outcome",
    [
        (ResultStatus.POSTPONED, Outcome.UNSETTLED),
        (ResultStatus.CANCELLED, Outcome.VOID),
        (ResultStatus.ABANDONED, Outcome.VOID),
        (ResultStatus.UNFINISHED, Outcome.UNSETTLED),
        (ResultStatus.UNKNOWN, Outcome.UNSETTLED),
    ],
)
@pytest.mark.parametrize("selection", list(Selection))
def test_special_states(status, outcome, selection):
    result = ResultObservation(
        provider_fixture_id=42, observed_at=datetime.now(UTC), provider_status=status, status=status
    )
    assert settle(selection, result) == outcome


@pytest.mark.parametrize("status", [ResultStatus.AFTER_EXTRA_TIME, ResultStatus.AFTER_PENALTIES])
@pytest.mark.parametrize("selection", list(Selection))
def test_extra_time_and_shootout_never_change_regulation(status, selection):
    ft = observation(regulation_home=1, regulation_away=1)
    extra = ft.model_copy(
        update={
            "status": status,
            "extra_time_home": 3,
            "extra_time_away": 1,
            "penalties_home": 5 if status == ResultStatus.AFTER_PENALTIES else None,
            "penalties_away": 4 if status == ResultStatus.AFTER_PENALTIES else None,
        }
    )
    assert settle(selection, extra) == settle(selection, ft)
    assert (
        settle(
            selection, extra.model_copy(update={"regulation_home": None, "regulation_away": None})
        )
        == Outcome.UNSETTLED
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"regulation_home": -1, "regulation_away": 1},
        {"regulation_home": True, "regulation_away": 1},
        {"regulation_home": 1.5, "regulation_away": 1},
        {"regulation_home": 1},
        {},
        {"regulation_home": 0, "regulation_away": 0, "extra_time_home": 1, "extra_time_away": 0},
    ],
)
def test_invalid_final_contract(kwargs):
    with pytest.raises(ValidationError):
        observation(**kwargs)


@pytest.mark.parametrize(
    "outcome,value",
    [
        (Outcome.WIN, 1.5),
        (Outcome.LOSS, -1),
        (Outcome.PUSH, 0),
        (Outcome.VOID, 0),
        (Outcome.UNSETTLED, None),
    ],
)
def test_fixed_return(outcome, value):
    assert fixed_return(outcome, 2.5) == value


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0, 1, -2, True])
def test_invalid_odds(bad):
    with pytest.raises(ValueError):
        fixed_return(Outcome.WIN, bad)
