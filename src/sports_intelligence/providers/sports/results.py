"""API-Football v3 result normalization, isolated from domain settlement."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ValidationError

from sports_intelligence.evaluation.settlement import ResultObservation, ResultStatus
from sports_intelligence.providers.errors import ProviderResponseError

STATUS_MAP = {
    "FT": ResultStatus.FINAL,
    "AET": ResultStatus.AFTER_EXTRA_TIME,
    "PEN": ResultStatus.AFTER_PENALTIES,
    "PST": ResultStatus.POSTPONED,
    "CANC": ResultStatus.CANCELLED,
    "ABD": ResultStatus.ABANDONED,
    **dict.fromkeys(
        ("NS", "TBD", "1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"),
        ResultStatus.UNFINISHED,
    ),
}


def parse_results(payload: dict[str, Any], observed_at: datetime) -> list[ResultObservation]:
    entries = payload.get("response")
    if not isinstance(entries, list):
        raise ProviderResponseError("result response must be a list")
    results = []
    for entry in entries:
        try:
            fixture = entry["fixture"]
            code = fixture["status"]["short"]
            score = entry.get("score") or {}
            values: dict[str, Any] = {}
            for key, prefix in (
                ("fulltime", "regulation"),
                ("extratime", "extra_time"),
                ("penalty", "penalties"),
            ):
                pair = score.get(key) or {}
                if not isinstance(pair, dict):
                    raise ValueError("invalid score block")
                values[prefix + "_home"] = pair.get("home")
                values[prefix + "_away"] = pair.get("away")
            results.append(
                ResultObservation(
                    provider_fixture_id=fixture["id"],
                    provider_home_team_id=(entry.get("teams") or {}).get("home", {}).get("id"),
                    provider_away_team_id=(entry.get("teams") or {}).get("away", {}).get("id"),
                    status=STATUS_MAP.get(code, ResultStatus.UNKNOWN),
                    provider_status=code,
                    observed_at=observed_at,
                    **values,
                )
            )
        except (AttributeError, KeyError, TypeError, ValueError, ValidationError) as exc:
            raise ProviderResponseError("malformed final-result contract") from exc
    if len({r.provider_fixture_id for r in results}) != len(results):
        raise ProviderResponseError("duplicate result identity in date batch")
    return results
