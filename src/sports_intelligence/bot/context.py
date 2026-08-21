from __future__ import annotations

from dataclasses import dataclass, field

from sports_intelligence.bot.backend_client import BackendClient
from sports_intelligence.bot.transport import TelegramTransport
from sports_intelligence.core.config import Settings


@dataclass(frozen=True)
class AppContext:
    """Dependencies shared by all Telegram handlers (injected by middleware)."""

    transport: TelegramTransport
    backend: BackendClient
    settings: Settings
    allowed_user_ids: frozenset[int] = field(default_factory=frozenset)
