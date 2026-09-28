"""Modelos y esquema de la base de datos (SQLite)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS activity (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp       TEXT    NOT NULL,
        assistant       TEXT,
        conversation_id TEXT,
        tool            TEXT    NOT NULL,
        arguments       TEXT    NOT NULL DEFAULT '{}',
        risk_level      TEXT    NOT NULL,
        status          TEXT    NOT NULL,
        message         TEXT,
        duration_ms     INTEGER,
        verified        INTEGER
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_activity_id_desc ON activity (id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_activity_tool ON activity (tool)",
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp       TEXT    NOT NULL,
        conversation_id TEXT    NOT NULL,
        assistant       TEXT    NOT NULL,
        role            TEXT    NOT NULL,
        content         TEXT    NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chat_conversation ON chat_messages (conversation_id, id)",
)


@dataclass(slots=True)
class ActivityRecord:
    """Una entrada del registro de actividad."""

    id: int
    timestamp: str
    tool: str
    arguments: dict[str, Any]
    risk_level: str
    status: str
    message: str | None = None
    assistant: str | None = None
    conversation_id: str | None = None
    duration_ms: int | None = None
    verified: bool | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ActivityRecord":
        try:
            arguments = json.loads(row["arguments"] or "{}")
        except (json.JSONDecodeError, TypeError):
            arguments = {}
        verified = row["verified"]
        return cls(
            id=row["id"],
            timestamp=row["timestamp"],
            tool=row["tool"],
            arguments=arguments if isinstance(arguments, dict) else {},
            risk_level=row["risk_level"],
            status=row["status"],
            message=row["message"],
            assistant=row["assistant"],
            conversation_id=row["conversation_id"],
            duration_ms=row["duration_ms"],
            verified=None if verified is None else bool(verified),
        )

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "assistant": self.assistant,
            "conversation_id": self.conversation_id,
            "tool": self.tool,
            "arguments": self.arguments,
            "risk_level": self.risk_level,
            "status": self.status,
            "message": self.message,
            "duration_ms": self.duration_ms,
            "verified": self.verified,
        }


@dataclass(slots=True)
class ChatMessageRecord:
    id: int
    timestamp: str
    conversation_id: str
    assistant: str
    role: str
    content: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ChatMessageRecord":
        return cls(
            id=row["id"],
            timestamp=row["timestamp"],
            conversation_id=row["conversation_id"],
            assistant=row["assistant"],
            role=row["role"],
            content=row["content"],
        )
