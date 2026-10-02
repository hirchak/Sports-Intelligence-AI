"""Request correlation without logging bodies, query strings or headers."""

from __future__ import annotations

import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sports_intelligence.core.logging import LOG_CONTEXT, get_logger

logger = get_logger(__name__)


class RequestObservability:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        supplied = (
            dict(scope.get("headers", []))
            .get(b"x-correlation-id", b"")
            .decode("ascii", errors="ignore")
        )
        correlation = (
            supplied if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", supplied) else str(uuid.uuid4())
        )
        token = LOG_CONTEXT.set({"correlation_id": correlation})
        started, status = time.monotonic(), 500

        async def observed_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-correlation-id", correlation.encode()),
                ]
            await send(message)

        try:
            await self.app(scope, receive, observed_send)
        finally:
            logger.info(
                "http request completed",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status_code": status,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                },
            )
            LOG_CONTEXT.reset(token)
