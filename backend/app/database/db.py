"""Acceso a SQLite.

Una única conexión protegida por lock (``check_same_thread=False``), con WAL para
que lecturas y escrituras no se estorben.  Las llamadas desde código async se
hacen en el threadpool (ver ``app.services.activity``).
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.config import get_settings
from app.database.models import SCHEMA_STATEMENTS


class Database:
    """Envoltorio fino sobre ``sqlite3`` pensado para uso local de escritorio."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._connection: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                self.path, check_same_thread=False, isolation_level=None, timeout=10.0
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute("PRAGMA foreign_keys=ON")
            self._connection = connection
        return self._connection

    def initialize(self) -> None:
        """Crea el esquema si no existe.  Idempotente."""

        with self._lock:
            cursor = self.connection.cursor()
            try:
                for statement in SCHEMA_STATEMENTS:
                    cursor.execute(statement)
            finally:
                cursor.close()

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        with self._lock:
            cursor = self.connection.cursor()
            try:
                yield cursor
            finally:
                cursor.close()

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None


_database: Database | None = None


def get_database() -> Database:
    """Base de datos compartida por la aplicación."""

    global _database
    if _database is None:
        _database = Database(get_settings().database_file)
        _database.initialize()
    return _database


def reset_database_for_tests(path: Path | str) -> Database:
    """Reemplaza la base de datos global.  Uso exclusivo en tests."""

    global _database
    if _database is not None:
        _database.close()
    _database = Database(path)
    _database.initialize()
    return _database
