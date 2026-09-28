"""Bus de eventos en memoria para el WebSocket ``/ws/events``.

El frontend usa estos eventos para animaciones y feedback inmediato.  El bus nunca
bloquea al productor: si un suscriptor va lento, se descartan sus eventos más
antiguos antes que frenar la ejecución de una acción.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

QUEUE_MAX_SIZE = 200
HISTORY_SIZE = 50


class EventType(str, Enum):
    ASSISTANT_STATUS = "assistant.status"
    ASSISTANT_SPEAKING = "assistant.speaking"
    ASSISTANT_SPOKEN = "assistant.spoken"
    SPEECH_PARTIAL = "speech.partial"
    SPEECH_HEARD = "speech.heard"
    ACTION_PLANNING = "action.planning"
    ACTION_STARTED = "action.started"
    ACTION_COMPLETED = "action.completed"
    ACTION_FAILED = "action.failed"
    CONFIRMATION_REQUIRED = "confirmation.required"
    SYSTEM_STATUS = "system.status"


class AssistantStatus(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING_CONFIRMATION = "waiting_confirmation"
    SUCCESS = "success"
    ERROR = "error"


@dataclass(slots=True)
class Event:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    sequence: int = 0
    timestamp: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "data": self.data,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
        }


class Subscription:
    """Cola de eventos de un cliente WebSocket."""

    def __init__(self, bus: "EventBus") -> None:
        self._bus = bus
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        self.dropped = 0

    async def get(self) -> Event:
        return await self.queue.get()

    def offer(self, event: Event) -> None:
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            self.dropped += 1
            try:  # se descarta el más antiguo para conservar el más reciente
                self.queue.get_nowait()
                self.queue.put_nowait(event)
            except (asyncio.QueueEmpty, asyncio.QueueFull):  # pragma: no cover
                pass

    def close(self) -> None:
        self._bus.unsubscribe(self)

    def __enter__(self) -> "Subscription":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class EventBus:
    """Publicador/suscriptor mínimo, sin dependencias externas."""

    def __init__(self, history_size: int = HISTORY_SIZE) -> None:
        self._subscribers: set[Subscription] = set()
        self._history: deque[Event] = deque(maxlen=history_size)
        self._counter = itertools.count(1)

    # ------------------------------------------------------------------
    def subscribe(self) -> Subscription:
        subscription = Subscription(self)
        self._subscribers.add(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        self._subscribers.discard(subscription)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def recent(self) -> list[Event]:
        return list(self._history)

    # ------------------------------------------------------------------
    def publish(self, event_type: EventType, data: dict[str, Any] | None = None) -> Event:
        """Publica un evento.  Seguro de llamar desde código sync o async."""

        event = Event(
            type=event_type,
            data=dict(data or {}),
            sequence=next(self._counter),
            timestamp=datetime.now().astimezone().isoformat(timespec="milliseconds"),
        )
        self._history.append(event)
        for subscription in tuple(self._subscribers):
            subscription.offer(event)
        return event

    def publish_status(self, status: AssistantStatus, **extra: Any) -> Event:
        return self.publish(EventType.ASSISTANT_STATUS, {"status": status.value, **extra})


#: Bus compartido por toda la aplicación.
event_bus = EventBus()
