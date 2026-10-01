from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sports_intelligence.predictions.config import LLMConfig, ModelSpec
from sports_intelligence.predictions.identity import fingerprint


class Health(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RATE_LIMITED = "RATE_LIMITED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class RoutingDecision:
    route_name: str
    selected: ModelSpec
    fallbacks: tuple[ModelSpec, ...]
    fingerprint: str
    audit: tuple[str, ...]


class ModelRouter:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def select(
        self,
        task: str,
        *,
        required_capabilities: tuple[str, ...] = ("structured_output",),
        quality_tier: str | None = None,
        budget_class: str | None = None,
        health: dict[tuple[str, str], Health] | None = None,
        override: str | None = None,
    ) -> RoutingDecision:
        name = override or task
        if override and override not in self.config.manual_override_routes:
            raise ValueError("manual route override not allowed")
        if name not in self.config.routes:
            raise ValueError("route not configured")
        route = self.config.routes[name]
        if quality_tier is not None and route.quality_tier != quality_tier:
            raise ValueError("route quality tier mismatch")
        if budget_class is not None and route.budget_class != budget_class:
            raise ValueError("route budget class mismatch")
        candidates = [route.primary, *route.fallbacks]
        available: list[ModelSpec] = []
        audit: list[str] = []
        for model in candidates:
            state = (health or {}).get((model.provider, model.model), Health.HEALTHY)
            if not set(required_capabilities).issubset(model.capabilities):
                audit.append(f"skip:{model.provider}:{model.model}:capabilities")
            elif state in (Health.RATE_LIMITED, Health.UNAVAILABLE):
                audit.append(f"skip:{model.provider}:{model.model}:{state.value}")
            else:
                available.append(model)
        if not available:
            raise ValueError("no eligible model route")
        # Preserve configured ordering, DEGRADED is usable and explicitly audited.
        audit.append(f"select:{available[0].provider}:{available[0].model}")
        return RoutingDecision(
            name,
            available[0],
            tuple(available[1:]),
            fingerprint(
                {
                    "version": self.config.version,
                    "task": task,
                    "route": name,
                    "config": route.model_dump(mode="json"),
                    "selection": available[0].hash,
                    "audit": audit,
                }
            ),
            tuple(audit),
        )
