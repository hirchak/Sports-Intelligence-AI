from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from sports_intelligence.evaluation.config import EvaluationConfig


def probability(p: float) -> float:
    if isinstance(p, bool) or not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError("invalid probability")
    return p


def binary_brier(p: float, y: int) -> float:
    if type(y) is not int or y not in (0, 1):
        raise ValueError("binary target required")
    return (probability(p) - y) ** 2


def binary_log_loss(p: float, y: int, epsilon: float = 1e-15) -> float:
    binary_brier(p, y)
    EvaluationConfig(epsilon=epsilon)
    q = min(1 - epsilon, max(epsilon, p))
    return -math.log(q) if y else -math.log1p(-q)


def multiclass_brier_sum(ps: Sequence[float], winner: int) -> float:
    if len(ps) != 3 or type(winner) is not int or winner not in range(3):
        raise ValueError("complete 1X2 required")
    if abs(math.fsum(probability(p) for p in ps) - 1) > 1e-6:
        raise ValueError("invalid 1X2 sum")
    return math.fsum(binary_brier(p, int(i == winner)) for i, p in enumerate(ps))


def bucket_index(p: float, boundaries: Sequence[float]) -> int:
    probability(p)
    for i, upper in enumerate(boundaries[1:]):
        if p < upper:
            return i
    return len(boundaries) - 2


@dataclass(frozen=True)
class Bucket:
    lower: float
    upper: float
    sample_size: int
    mean_probability: float | None
    event_frequency: float | None
    gap: float | None


def calibration(samples: Sequence[tuple[float, int]], config: EvaluationConfig) -> list[Bucket]:
    groups: list[list[tuple[float, int]]] = [[] for _ in config.calibration_boundaries[1:]]
    for p, y in samples:
        binary_brier(p, y)
        groups[bucket_index(p, config.calibration_boundaries)].append((p, y))
    output = []
    for i, group in enumerate(groups):
        n = len(group)
        mp = math.fsum(p for p, _ in group) / n if n else None
        freq = math.fsum(y for _, y in group) / n if n else None
        output.append(
            Bucket(
                config.calibration_boundaries[i],
                config.calibration_boundaries[i + 1],
                n,
                mp,
                freq,
                mp - freq if mp is not None and freq is not None else None,
            )
        )
    return output


def probability_metrics(
    samples: Sequence[tuple[float, int]], config: EvaluationConfig
) -> dict[str, float | None]:
    n = len(samples)
    buckets = calibration(samples, config)
    return {
        "binary_brier": math.fsum(binary_brier(p, y) for p, y in samples) / n if n else None,
        "binary_log_loss": math.fsum(binary_log_loss(p, y, config.epsilon) for p, y in samples) / n
        if n
        else None,
        "calibration_ece": math.fsum(b.sample_size * abs(b.gap or 0) for b in buckets) / n
        if n
        else None,
        "sharpness_mean_squared_distance_from_half": math.fsum((p - 0.5) ** 2 for p, _ in samples)
        / n
        if n
        else None,
    }


def closing_price_proxy(captured_odds: float, closing_odds: float) -> float:
    """Research price comparison only; caller proves snapshot availability and identity."""
    for value in (captured_odds, closing_odds):
        if isinstance(value, bool) or not math.isfinite(value) or value <= 1:
            raise ValueError("invalid closing price proxy odds")
    return captured_odds / closing_odds - 1
