import sqlite3
import threading
from pathlib import Path
from typing import Iterable, Optional


class Database:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
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
