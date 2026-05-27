import json
import time
import uuid
from typing import Any, Dict, Optional

from .database import Database
from .models import SessionRecord


class SessionStore:
    def __init__(self, db_path: str, ttl_seconds: int = 7200) -> None:
        self._db = Database(db_path)
        self._ttl_seconds = ttl_seconds

    def get(self, session_id: str) -> Optional[SessionRecord]:
        self.prune()
        row = self._db.fetch_one(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        if row is None:
            return None
        return self._row_to_record(row)

    def get_or_create(self, session_id: Optional[str], model_profile: Optional[str] = None) -> SessionRecord:
        self.prune()
        session_id = session_id or str(uuid.uuid4())
        row = self._db.fetch_one(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        now = time.time()
        if row is None:
            self._db.execute(
                """
                INSERT INTO sessions (session_id, total_tokens, model_profile, created_at, last_updated, optimization_stats)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, 0, model_profile, now, now, None),
            )
            return SessionRecord(
                session_id=session_id,
                total_tokens=0,
                model_profile=model_profile,
                created_at=now,
                last_updated=now,
                optimization_stats={},
            )

        record = self._row_to_record(row)
        if model_profile and model_profile != record.model_profile:
            record.model_profile = model_profile
            self._db.execute(
                "UPDATE sessions SET model_profile = ?, last_updated = ? WHERE session_id = ?",
                (model_profile, now, session_id),
            )
        else:
            self._db.execute(
                "UPDATE sessions SET last_updated = ? WHERE session_id = ?",
                (now, session_id),
            )
        record.last_updated = now
        return record

    def commit_tokens(self, session_id: Optional[str], delta_tokens: int, model_profile: Optional[str] = None) -> SessionRecord:
        if delta_tokens <= 0:
            raise ValueError("delta_tokens must be > 0")
        session = self.get_or_create(session_id, model_profile)
        new_total = session.total_tokens + delta_tokens
        now = time.time()
        self._db.execute(
            "UPDATE sessions SET total_tokens = ?, model_profile = ?, last_updated = ? WHERE session_id = ?",
            (new_total, model_profile or session.model_profile, now, session.session_id),
        )
        session.total_tokens = new_total
        session.last_updated = now
        if model_profile:
            session.model_profile = model_profile
        return session

    def reset_session(self, session_id: str, model_profile: Optional[str] = None) -> SessionRecord:
        session = self.get_or_create(session_id, model_profile)
        now = time.time()
        self._db.execute(
            "UPDATE sessions SET total_tokens = ?, model_profile = ?, last_updated = ? WHERE session_id = ?",
            (0, model_profile or session.model_profile, now, session.session_id),
        )
        session.total_tokens = 0
        session.last_updated = now
        if model_profile:
            session.model_profile = model_profile
        return session

    def update_optimization_stats(self, session_id: str, stats: Dict[str, Any]) -> None:
        self.get_or_create(session_id)
        now = time.time()
        payload = json.dumps(stats)
        self._db.execute(
            "UPDATE sessions SET optimization_stats = ?, last_updated = ? WHERE session_id = ?",
            (payload, now, session_id),
        )

    def prune(self) -> None:
        if self._ttl_seconds <= 0:
            return
        cutoff = time.time() - self._ttl_seconds
        self._db.execute("DELETE FROM sessions WHERE last_updated < ?", (cutoff,))

    @staticmethod
    def _row_to_record(row) -> SessionRecord:
        stats = None
        if row["optimization_stats"]:
            try:
                stats = json.loads(row["optimization_stats"])
            except json.JSONDecodeError:
                stats = None
        return SessionRecord(
            session_id=row["session_id"],
            total_tokens=row["total_tokens"],
            model_profile=row["model_profile"],
            created_at=row["created_at"],
            last_updated=row["last_updated"],
            optimization_stats=stats or {},
        )
