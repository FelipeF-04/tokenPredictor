import sqlite3
import threading
from pathlib import Path
from typing import Callable, Iterable, Optional, TypeVar


T = TypeVar("T")


class Database:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        return connection

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode=WAL;")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    total_tokens INTEGER NOT NULL,
                    model_profile TEXT,
                    created_at REAL NOT NULL,
                    last_updated REAL NOT NULL,
                    optimization_stats TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(last_updated)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_events (
                    session_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    token_count INTEGER NOT NULL CHECK (token_count >= 0),
                    content_hash TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (session_id, event_id),
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversation_events_session_created
                ON conversation_events(session_id, created_at)
                """
            )
            connection.commit()
        finally:
            connection.close()

    def execute(self, statement: str, parameters: Iterable = ()) -> None:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute(statement, tuple(parameters))
                connection.commit()
            finally:
                connection.close()

    def fetch_one(self, statement: str, parameters: Iterable = ()) -> Optional[sqlite3.Row]:
        with self._lock:
            connection = self._connect()
            try:
                cursor = connection.execute(statement, tuple(parameters))
                return cursor.fetchone()
            finally:
                connection.close()

    def fetch_all(self, statement: str, parameters: Iterable = ()) -> Iterable[sqlite3.Row]:
        with self._lock:
            connection = self._connect()
            try:
                cursor = connection.execute(statement, tuple(parameters))
                return cursor.fetchall()
            finally:
                connection.close()

    def run_transaction(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                result = operation(connection)
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()
