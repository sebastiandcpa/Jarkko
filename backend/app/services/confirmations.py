"""Almacén de confirmaciones pendientes.

Las acciones de riesgo alto no se ejecutan hasta que el usuario confirma.  Se
guarda la petición **original** (sin validar) y se vuelve a validar en el momento
de ejecutar: el sistema de archivos puede haber cambiado entre ambos instantes.

Cada confirmación es de un solo uso y caduca.
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.config import get_settings
from app.utils.redaction import sanitize_arguments


class ConfirmationError(Exception):
    """La confirmación no existe, ya se usó o caducó."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(slots=True)
class PendingConfirmation:
    id: str
    tool: str
    arguments: dict[str, Any]
    risk_level: str
    description: str
    created_at: datetime
    expires_at: datetime
    assistant: str = "jarkko"
    conversation_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def expired(self) -> bool:
        return datetime.now() >= self.expires_at

    def to_public(self) -> dict[str, Any]:
        return {
            "confirmation_id": self.id,
            "tool": self.tool,
            "arguments": sanitize_arguments(self.arguments),
            "risk_level": self.risk_level,
            "description": self.description,
            "assistant": self.assistant,
            "conversation_id": self.conversation_id,
            "created_at": self.created_at.astimezone().isoformat(timespec="seconds"),
            "expires_at": self.expires_at.astimezone().isoformat(timespec="seconds"),
        }


class ConfirmationStore:
    """Registro en memoria de confirmaciones pendientes (proceso local)."""

    def __init__(self, ttl_seconds: int | None = None) -> None:
        self._items: dict[str, PendingConfirmation] = {}
        self._lock = threading.Lock()
        self._ttl_override = ttl_seconds

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_override or get_settings().confirmation_ttl_seconds

    # ------------------------------------------------------------------
    def create(
        self,
        *,
        tool: str,
        arguments: dict[str, Any],
        risk_level: str,
        description: str,
        assistant: str = "jarkko",
        conversation_id: str | None = None,
    ) -> PendingConfirmation:
        now = datetime.now()
        pending = PendingConfirmation(
            id=secrets.token_urlsafe(16),
            tool=tool,
            arguments=dict(arguments),
            risk_level=risk_level,
            description=description,
            created_at=now,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
            assistant=assistant,
            conversation_id=conversation_id,
        )
        with self._lock:
            self._purge_locked()
            self._items[pending.id] = pending
        return pending

    def get(self, confirmation_id: str) -> PendingConfirmation | None:
        with self._lock:
            self._purge_locked()
            return self._items.get(confirmation_id)

    def consume(self, confirmation_id: str) -> PendingConfirmation:
        """Devuelve y elimina la confirmación.  Un solo uso."""

        with self._lock:
            self._purge_locked()
            pending = self._items.pop(confirmation_id, None)
        if pending is None:
            raise ConfirmationError(
                "La confirmación no existe o ya caducó.", code="confirmation_not_found"
            )
        if pending.expired:
            raise ConfirmationError("La confirmación caducó.", code="confirmation_expired")
        return pending

    def cancel(self, confirmation_id: str) -> PendingConfirmation:
        return self.consume(confirmation_id)

    def pending(self) -> list[PendingConfirmation]:
        with self._lock:
            self._purge_locked()
            return sorted(self._items.values(), key=lambda item: item.created_at)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    # ------------------------------------------------------------------
    def _purge_locked(self) -> None:
        expired = [key for key, value in self._items.items() if value.expired]
        for key in expired:
            self._items.pop(key, None)


#: Almacén compartido.
confirmation_store = ConfirmationStore()
