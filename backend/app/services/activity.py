"""Registro de actividad y de conversación (persistencia en SQLite).

Todo lo que el asistente ejecuta queda registrado con su nivel de riesgo y su
resultado.  Los argumentos se sanean antes de guardarse: nunca se persisten
contraseñas, tokens ni API keys.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.database.db import Database, get_database
from app.database.models import ActivityRecord, ChatMessageRecord
from app.providers.base import ChatTurn
from app.utils.redaction import sanitize_arguments
from app.utils.text import truncate


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class ActivityService:
    """Escritura y lectura del historial."""

    def __init__(self, database: Database | None = None) -> None:
        self._database = database

    @property
    def database(self) -> Database:
        return self._database or get_database()

    # ------------------------------------------------------------------
    # escritura
    # ------------------------------------------------------------------
    def record_sync(
        self,
        *,
        tool: str,
        arguments: Mapping[str, Any] | None,
        risk_level: str,
        status: str,
        message: str | None = None,
        assistant: str | None = None,
        conversation_id: str | None = None,
        duration_ms: int | None = None,
        verified: bool | None = None,
    ) -> int:
        payload = json.dumps(sanitize_arguments(arguments), ensure_ascii=False)
        with self.database.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO activity (
                    timestamp, assistant, conversation_id, tool, arguments,
                    risk_level, status, message, duration_ms, verified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now(),
                    assistant,
                    conversation_id,
                    tool,
                    payload,
                    risk_level,
                    status,
                    truncate(message or "", 1000),
                    duration_ms,
                    None if verified is None else int(verified),
                ),
            )
            return int(cursor.lastrowid or 0)

    async def record(self, **kwargs: Any) -> int:
        return await run_in_threadpool(lambda: self.record_sync(**kwargs))

    def log_message_sync(
        self, *, conversation_id: str, assistant: str, role: str, content: str
    ) -> None:
        with self.database.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chat_messages (timestamp, conversation_id, assistant, role, content)
                VALUES (?, ?, ?, ?, ?)
                """,
                (_now(), conversation_id, assistant, role, truncate(content, 4000)),
            )

    async def log_message(self, **kwargs: Any) -> None:
        await run_in_threadpool(lambda: self.log_message_sync(**kwargs))

    # ------------------------------------------------------------------
    # lectura
    # ------------------------------------------------------------------
    def recent_sync(
        self, *, limit: int = 50, tool: str | None = None, status: str | None = None
    ) -> list[ActivityRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if tool:
            clauses.append("tool = ?")
            params.append(tool)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self.database.cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM activity {where} ORDER BY id DESC LIMIT ?", tuple(params)
            )
            return [ActivityRecord.from_row(row) for row in cursor.fetchall()]

    async def recent(self, **kwargs: Any) -> list[ActivityRecord]:
        return await run_in_threadpool(lambda: self.recent_sync(**kwargs))

    def history_sync(self, conversation_id: str, *, limit: int = 10) -> list[ChatTurn]:
        with self.database.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM chat_messages
                WHERE conversation_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (conversation_id, limit),
            )
            rows = [ChatMessageRecord.from_row(row) for row in cursor.fetchall()]
        return [ChatTurn(role=row.role, content=row.content) for row in reversed(rows)]

    async def history(self, conversation_id: str, *, limit: int = 10) -> list[ChatTurn]:
        return await run_in_threadpool(lambda: self.history_sync(conversation_id, limit=limit))

    def stats_sync(self) -> dict[str, Any]:
        with self.database.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM activity")
            total = int(cursor.fetchone()["total"])
            cursor.execute(
                "SELECT status, COUNT(*) AS count FROM activity GROUP BY status ORDER BY count DESC"
            )
            by_status = {row["status"]: int(row["count"]) for row in cursor.fetchall()}
            cursor.execute(
                "SELECT tool, COUNT(*) AS count FROM activity GROUP BY tool ORDER BY count DESC LIMIT 5"
            )
            top_tools = [{"tool": row["tool"], "count": int(row["count"])} for row in cursor.fetchall()]
        return {"total": total, "by_status": by_status, "top_tools": top_tools}

    async def stats(self) -> dict[str, Any]:
        return await run_in_threadpool(self.stats_sync)


#: Servicio compartido (usa la base de datos global de forma perezosa).
activity_service = ActivityService()
