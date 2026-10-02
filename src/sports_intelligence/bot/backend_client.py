from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel

from sports_intelligence.core.logging import get_logger
from sports_intelligence.predictions.contracts import Role, Variant
from sports_intelligence.schemas.evaluation import (
    EvaluationSummaryView,
    ResultDetailView,
    ResultView,
    SettlementView,
)
from sports_intelligence.schemas.predictions import (
    AnalyzeResponse,
    PredictionDetail,
    PredictionSummary,
)

logger = get_logger(__name__)


class BackendClientError(Exception):
    """Base class for bot-safe backend client failures."""


class BackendUnavailableError(BackendClientError):
    """Network failure or timeout while talking to the backend."""


class BackendResponseError(BackendClientError):
    """Unexpected backend HTTP status (body intentionally not exposed)."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"backend responded with status {status_code}")


class BackendPayloadError(BackendClientError):
    """Backend payload did not match the expected shape."""


class HealthStatus(BaseModel):
    api: bool
    database: bool | None = None
    redis: bool | None = None


class FixtureView(BaseModel):
    id: UUID
    league_slug: str
    home_team: str | None = None
    away_team: str | None = None
    kickoff_at: datetime
    venue: str | None = None
    round: str | None = None
    status: str


class DiscoverResult(BaseModel):
    job_id: UUID
    status: str
    already_queued: bool


class BackendClient:
    """Typed internal HTTP client over the FastAPI control plane.

    Only the endpoints needed by the M3 Telegram UI are implemented.
    All failures are normalized into bot-safe BackendClientError
    subclasses that never carry URLs, bodies or internal details.
    """

    def __init__(
        self,
        base_url: str,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None

    async def __aenter__(self) -> BackendClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def health(self) -> HealthStatus:
        try:
            response = await self._client.get(f"{self._base_url}/health")
        except httpx.HTTPError:
            return HealthStatus(api=False)
        if response.status_code != 200:
            return HealthStatus(api=False)
        database: bool | None = None
        redis: bool | None = None
        try:
            ready = await self._client.get(f"{self._base_url}/ready")
            payload = ready.json()
            checks = payload.get("checks") or {}
            if isinstance(checks, dict):
                if checks.get("database") == "ok":
                    database = True
                elif "database" in checks:
                    database = False
                if checks.get("redis") == "ok":
                    redis = True
                elif "redis" in checks:
                    redis = False
        except (httpx.HTTPError, ValueError, AttributeError):
            logger.warning("backend readiness probe failed", exc_info=True)
        return HealthStatus(api=True, database=database, redis=redis)

    async def list_fixtures(self, fixture_date: date | None = None) -> list[FixtureView]:
        params: dict[str, str] = {}
        if fixture_date is not None:
            params["date"] = fixture_date.isoformat()
        payload = await self._get_json("/v1/fixtures", params=params)
        if not isinstance(payload, list):
            raise BackendPayloadError("fixtures payload is not a list")
        try:
            return [FixtureView.model_validate(item) for item in payload]
        except ValueError as exc:
            raise BackendPayloadError("unexpected fixture payload") from exc

    async def get_fixture(self, fixture_id: str) -> FixtureView | None:
        try:
            response = await self._client.get(f"{self._base_url}/v1/fixtures/{fixture_id}")
        except httpx.HTTPError as exc:
            raise BackendUnavailableError("backend is unreachable") from exc
        if response.status_code == 404:
            return None
        self._ensure_status(response, 200)
        try:
            return FixtureView.model_validate(response.json())
        except ValueError as exc:
            raise BackendPayloadError("unexpected fixture payload") from exc

    async def discover(self, fixture_date: date) -> DiscoverResult:
        payload = await self._post_json(
            "/v1/jobs/discover", body={"date": fixture_date.isoformat()}
        )
        if not isinstance(payload, dict):
            raise BackendPayloadError("discovery payload is not an object")
        try:
            return DiscoverResult.model_validate(payload)
        except ValueError as exc:
            raise BackendPayloadError("unexpected discovery payload") from exc

    async def list_predictions(
        self,
        *,
        fixture_id: str | None = None,
        limit: int = 8,
    ) -> list[PredictionSummary]:
        params = {"role": "PRIMARY", "limit": str(limit)}
        if fixture_id:
            params["fixture_id"] = fixture_id
        payload = await self._get_json("/v1/predictions", params=params)
        try:
            if not isinstance(payload, list):
                raise ValueError("list required")
            return [PredictionSummary.model_validate(row) for row in payload]
        except ValueError:
            raise BackendPayloadError("unexpected prediction list") from None

    async def get_prediction(self, run_id: str) -> PredictionDetail:
        payload = await self._get_json(f"/v1/predictions/{run_id}")
        try:
            return PredictionDetail.model_validate(payload)
        except ValueError:
            raise BackendPayloadError("unexpected prediction detail") from None

    async def analyze_fixture(
        self,
        fixture_id: str,
        *,
        context_id: UUID | None = None,
        phase: str = "MORNING",
        role: Role = Role.PRIMARY,
        variant: Variant = Variant.WITH_ODDS,
        rerun_key: UUID | None = None,
    ) -> AnalyzeResponse:
        body = {
            "phase": phase,
            "role": role.value,
            "variant": variant.value,
            "context_id": str(context_id) if context_id else None,
            "rerun": rerun_key is not None,
            "rerun_key": str(rerun_key) if rerun_key else None,
        }
        payload = await self._post_json(
            f"/v1/fixtures/{fixture_id}/analyze", body=body, expected=202
        )
        try:
            return AnalyzeResponse.model_validate(payload)
        except ValueError:
            raise BackendPayloadError("unexpected analyze response") from None

    async def evaluation_summary(
        self, *, period: str = "30d", group_by: str | None = None
    ) -> dict[str, Any]:
        params = {"period": period, "limit": "8"}
        if group_by:
            params["group_by"] = group_by
        payload = await self._get_json("/v1/evaluations/summary", params=params)
        if not isinstance(payload, dict) or not isinstance(payload.get("groups"), list):
            raise BackendPayloadError("invalid evaluation summary")
        try:
            EvaluationSummaryView.model_validate(payload)
        except ValueError:
            raise BackendPayloadError("invalid evaluation summary") from None
        return payload

    async def recent_results(self) -> list[dict[str, Any]]:
        payload = await self._get_json("/v1/results", params={"limit": "8"})
        if not isinstance(payload, list):
            raise BackendPayloadError("invalid result list")
        try:
            return [ResultView.model_validate(row).model_dump(mode="json") for row in payload]
        except ValueError:
            raise BackendPayloadError("invalid result list") from None

    async def result_detail(self, fixture_id: str) -> dict[str, Any]:
        payload = await self._get_json(f"/v1/results/{fixture_id}")
        if not isinstance(payload, dict):
            raise BackendPayloadError("invalid result detail")
        try:
            ResultDetailView.model_validate(payload)
        except ValueError:
            raise BackendPayloadError("invalid result detail") from None
        return payload

    async def settlements(self, fixture_id: str) -> list[dict[str, Any]]:
        payload = await self._get_json(
            f"/v1/results/{fixture_id}/settlements", params={"limit": "24"}
        )
        if not isinstance(payload, list):
            raise BackendPayloadError("invalid settlements")
        try:
            return [SettlementView.model_validate(row).model_dump(mode="json") for row in payload]
        except ValueError:
            raise BackendPayloadError("invalid settlements") from None

    async def evaluate(self) -> dict[str, Any]:
        payload = await self._post_json("/v1/jobs/evaluate", body={"period": "30d"}, expected=202)
        if not isinstance(payload, dict):
            raise BackendPayloadError("invalid evaluation request")
        return payload

    async def experiment_list(self, offset: int = 0) -> list[dict[str, Any]]:
        payload = await self._get_json(
            "/v1/experiments", params={"limit": "8", "offset": str(offset)}
        )
        return self._m9_rows(payload, ("id", "name", "status"))

    async def improvement_list(self, offset: int = 0) -> list[dict[str, Any]]:
        payload = await self._get_json(
            "/v1/improvements", params={"limit": "8", "offset": str(offset)}
        )
        rows = self._m9_rows(payload, ("id", "title", "status", "risk_level"))
        if any(type(row.get("sample_size")) is not int or row["sample_size"] < 0 for row in rows):
            raise BackendPayloadError("invalid proposal sample")
        return rows

    async def experiment_view(self, identity: str) -> dict[str, Any]:
        payload = await self._get_json(f"/v1/experiments/{UUID(identity)}")
        self._m9_rows([payload], ("id", "name", "status"))
        if not isinstance(payload.get("definition"), dict) or not isinstance(
            payload.get("runs"), list
        ):
            raise BackendPayloadError("invalid experiment detail")
        return self._m9_rows([payload], ("id", "status"))[0]

    async def improvement_view(self, identity: str) -> dict[str, Any]:
        payload = await self._get_json(f"/v1/improvements/{UUID(identity)}")
        self._m9_rows([payload], ("id", "title", "status", "problem", "hypothesis", "test_plan"))
        if type(payload.get("sample_size")) is not int or payload["sample_size"] < 0:
            raise BackendPayloadError("invalid proposal detail")
        if type(payload.get("automatic_experiment_supported")) is not bool or payload.get(
            "approval_requirement"
        ) not in (
            "registered_candidate_prompt",
            "reviewed_model_definition",
            "unsupported_component",
        ):
            raise BackendPayloadError("invalid proposal approval advice")
        return self._m9_rows([payload], ("id", "status"))[0]

    async def improvement_action(self, identity: str, action: str, actor: str) -> dict[str, Any]:
        if action not in ("approve-experiment", "reject"):
            raise ValueError("invalid improvement action")
        payload = await self._post_json(
            f"/v1/improvements/{UUID(identity)}/{action}",
            body={
                "actor": actor,
                "reason": "Manual Telegram " + action,
            },
        )
        self._m9_rows([payload], ("id", "title", "status"))
        return self._m9_rows([payload], ("id", "status"))[0]

    @staticmethod
    def _m9_rows(payload: Any, fields: tuple[str, ...]) -> list[dict[str, Any]]:
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise BackendPayloadError("invalid experiment/proposal response")
        for row in payload:
            if any(not isinstance(row.get(k), str) for k in fields):
                raise BackendPayloadError("invalid experiment/proposal fields")
            try:
                UUID(row["id"])
            except ValueError:
                raise BackendPayloadError("invalid experiment/proposal identity") from None
        return payload

    async def _get_json(self, path: str, params: dict[str, str] | None = None) -> Any:
        try:
            response = await self._client.get(f"{self._base_url}{path}", params=params)
        except httpx.HTTPError as exc:
            raise BackendUnavailableError("backend is unreachable") from exc
        self._ensure_status(response, 200)
        try:
            return response.json()
        except ValueError as exc:
            raise BackendPayloadError("backend returned malformed JSON") from exc

    async def _post_json(self, path: str, body: dict[str, Any], expected: int = 200) -> Any:
        try:
            response = await self._client.post(f"{self._base_url}{path}", json=body)
        except httpx.HTTPError as exc:
            raise BackendUnavailableError("backend is unreachable") from exc
        self._ensure_status(response, expected)
        try:
            return response.json()
        except ValueError as exc:
            raise BackendPayloadError("backend returned malformed JSON") from exc

    @staticmethod
    def _ensure_status(response: httpx.Response, expected: int) -> None:
        if response.status_code != expected:
            raise BackendResponseError(response.status_code)
