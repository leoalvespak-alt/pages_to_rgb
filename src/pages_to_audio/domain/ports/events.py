"""Event publisher port — SSE §38."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class DomainEvent:
    event_type: str
    session_id: str
    payload: dict[str, Any]


class EventPublisher(Protocol):
    async def publish(self, event: DomainEvent) -> None: ...
