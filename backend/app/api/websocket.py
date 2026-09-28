"""WebSocket ``/ws/events``: eventos en tiempo real para el frontend.

Tipos emitidos: ``assistant.status``, ``action.planning``, ``action.started``,
``action.completed``, ``action.failed``, ``confirmation.required`` y
``system.status``.

Formato de cada mensaje::

    {"type": "assistant.status", "data": {"status": "executing"}, "sequence": 12,
     "timestamp": "2026-09-27T16:45:10.123+02:00"}
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.services.confirmations import confirmation_store
from app.services.events import (
    AssistantStatus,
    Event,
    EventType,
    Subscription,
    event_bus,
)
from app.tools.system.handlers import snapshot

logger = logging.getLogger(__name__)

router = APIRouter()


def _envelope(event_type: EventType, data: dict) -> dict:
    return Event(type=event_type, data=data, sequence=0, timestamp="").to_public()


async def _send_initial_state(websocket: WebSocket) -> None:
    """Estado inicial para que el frontend pinte algo sin esperar eventos."""

    await websocket.send_json(
        _envelope(EventType.ASSISTANT_STATUS, {"status": AssistantStatus.IDLE.value})
    )
    await websocket.send_json(_envelope(EventType.SYSTEM_STATUS, await run_in_threadpool(snapshot)))
    for pending in confirmation_store.pending():
        await websocket.send_json(_envelope(EventType.CONFIRMATION_REQUIRED, pending.to_public()))


async def _pump_events(websocket: WebSocket, subscription: Subscription) -> None:
    while True:
        event = await subscription.get()
        await websocket.send_json(event.to_public())


async def _drain_incoming(websocket: WebSocket) -> None:
    """Lee los mensajes del cliente.

    El canal es de salida; solo se admite ``ping`` para mantener la conexión viva.
    Leer también permite detectar la desconexión de inmediato.
    """

    while True:
        message = await websocket.receive_text()
        if message.strip().lower() in {"ping", '"ping"', "{\"type\":\"ping\"}"}:
            await websocket.send_json(_envelope(EventType.ASSISTANT_STATUS, {"status": "pong"}))


@router.websocket("/ws/events")
async def events_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    subscription = event_bus.subscribe()
    try:
        await _send_initial_state(websocket)
        tasks = [
            asyncio.create_task(_pump_events(websocket, subscription)),
            asyncio.create_task(_drain_incoming(websocket)),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            exception = task.exception()
            if exception and not isinstance(exception, WebSocketDisconnect):
                raise exception
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 - una conexión caída no debe ensuciar los logs de error
        logger.debug("Conexión WebSocket terminada con error", exc_info=True)
    finally:
        subscription.close()


async def system_status_broadcaster() -> None:
    """Tarea de fondo: publica ``system.status`` mientras haya clientes conectados."""

    interval = max(1.0, get_settings().system_status_interval)
    while True:
        try:
            await asyncio.sleep(interval)
            if event_bus.subscriber_count == 0:
                continue
            event_bus.publish(EventType.SYSTEM_STATUS, await run_in_threadpool(snapshot))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - el broadcaster nunca debe morir
            logger.exception("Fallo publicando system.status")
