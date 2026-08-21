from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel

from sports_intelligence.core.logging import get_logger

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

    async def _post_json(self, path: str, body: dict[str, Any]) -> Any:
        try:
            response = await self._client.post(f"{self._base_url}{path}", json=body)
        except httpx.HTTPError as exc:
            raise BackendUnavailableError("backend is unreachable") from exc
        self._ensure_status(response, 200)
        try:
            return response.json()
        except ValueError as exc:
            raise BackendPayloadError("backend returned malformed JSON") from exc

    @staticmethod
    def _ensure_status(response: httpx.Response, expected: int) -> None:
        if response.status_code != expected:
            raise BackendResponseError(response.status_code)
