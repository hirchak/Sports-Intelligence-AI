from __future__ import annotations

import math
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from sports_intelligence.predictions.contracts import Selection, StrictModel

Score = Annotated[int, Field(strict=True, ge=0, le=100)]


class ResultStatus(StrEnum):
    FINAL = "FINAL"
    AFTER_EXTRA_TIME = "AFTER_EXTRA_TIME"
    AFTER_PENALTIES = "AFTER_PENALTIES"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"
    ABANDONED = "ABANDONED"
    UNFINISHED = "UNFINISHED"
    UNKNOWN = "UNKNOWN"


class Outcome(StrEnum):
    WIN = "WIN"
    LOSS = "LOSS"
    PUSH = "PUSH"
    VOID = "VOID"
    UNSETTLED = "UNSETTLED"


class ResultObservation(StrictModel):
    provider_fixture_id: Annotated[int, Field(strict=True, gt=0)]
    provider_home_team_id: Annotated[int, Field(strict=True, gt=0)] | None = None
    provider_away_team_id: Annotated[int, Field(strict=True, gt=0)] | None = None
    status: ResultStatus
    provider_status: Annotated[str, Field(min_length=1, max_length=32)]
    regulation_home: Score | None = None
    regulation_away: Score | None = None
    extra_time_home: Score | None = None
    extra_time_away: Score | None = None
    penalties_home: Score | None = None
    penalties_away: Score | None = None
    observed_at: datetime
    normalizer_version: str = "result_v1"

    @field_validator("observed_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("result observation needs timezone")
        return value

    @model_validator(mode="after")
    def consistent(self) -> ResultObservation:
        if (self.provider_home_team_id is None) != (self.provider_away_team_id is None):
            raise ValueError("partial team identity pair")
        for a, b in (
            (self.regulation_home, self.regulation_away),
            (self.extra_time_home, self.extra_time_away),
            (self.penalties_home, self.penalties_away),
        ):
            if (a is None) != (b is None):
                raise ValueError("partial score pair")
        if self.status == ResultStatus.FINAL and self.regulation_home is None:
            raise ValueError("FT must have a regulation score")
        if self.status == ResultStatus.FINAL and (
            self.extra_time_home is not None or self.penalties_home is not None
        ):
            raise ValueError("FT cannot include extra time or penalties")
        if self.status == ResultStatus.AFTER_EXTRA_TIME and self.penalties_home is not None:
            raise ValueError("AET cannot include shootout")
        if (
            self.status in (ResultStatus.POSTPONED, ResultStatus.CANCELLED)
            and self.regulation_home is not None
        ):
            raise ValueError("cancelled/postponed cannot assert a final score")
        return self


def settle(
    selection: Selection, result: ResultObservation, version: str = "regulation_v1"
) -> Outcome:
    if version != "regulation_v1":
        raise ValueError("unsupported settlement policy")
    result = ResultObservation.model_validate(result.model_dump())
    selection = Selection(selection)
    if result.status in (ResultStatus.CANCELLED, ResultStatus.ABANDONED):
        return Outcome.VOID
    if result.status not in (
        ResultStatus.FINAL,
        ResultStatus.AFTER_EXTRA_TIME,
        ResultStatus.AFTER_PENALTIES,
    ):
        return Outcome.UNSETTLED
    h, a = result.regulation_home, result.regulation_away
    if h is None or a is None:
        return Outcome.UNSETTLED
    truth = {
        Selection.HOME: h > a,
        Selection.DRAW: h == a,
        Selection.AWAY: h < a,
        Selection.HOME_OR_DRAW: h >= a,
        Selection.HOME_OR_AWAY: h != a,
        Selection.DRAW_OR_AWAY: h <= a,
        Selection.OVER_1_5: h + a >= 2,
        Selection.UNDER_1_5: h + a < 2,
        Selection.OVER_2_5: h + a >= 3,
        Selection.UNDER_2_5: h + a < 3,
        Selection.BTTS_YES: h > 0 and a > 0,
        Selection.BTTS_NO: h == 0 or a == 0,
    }
    return Outcome.WIN if truth[selection] else Outcome.LOSS


def fixed_return(outcome: Outcome, odds: float) -> float | None:
    outcome = Outcome(outcome)
    if isinstance(odds, bool) or not math.isfinite(odds) or odds <= 1:
        raise ValueError("invalid captured decimal odds")
    return {
        Outcome.WIN: odds - 1,
        Outcome.LOSS: -1.0,
        Outcome.PUSH: 0.0,
        Outcome.VOID: 0.0,
        Outcome.UNSETTLED: None,
    }[outcome]
