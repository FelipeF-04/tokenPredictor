import json
import time
import uuid
from typing import Any, Dict, List, Optional

from .database import Database
from .models import ConversationEventRecord, LedgerWriteResult, SessionRecord


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
        resolved_session_id = session_id or str(uuid.uuid4())

        def operation(connection):
            now = time.time()
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (resolved_session_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO sessions (
                        session_id, total_tokens, model_profile, created_at,
                        last_updated, optimization_stats
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (resolved_session_id, 0, model_profile, now, now, None),
                )
                return SessionRecord(
                    session_id=resolved_session_id,
                    total_tokens=0,
                    model_profile=model_profile,
                    created_at=now,
                    last_updated=now,
                    optimization_stats={},
                )

            record = self._row_to_record(row)
            resolved_profile = model_profile or record.model_profile
            connection.execute(
                """
                UPDATE sessions
                SET model_profile = ?, last_updated = ?
                WHERE session_id = ?
                """,
                (resolved_profile, now, resolved_session_id),
            )
            record.model_profile = resolved_profile
            record.last_updated = now
            return record

        return self._db.run_transaction(operation)

    def commit_tokens(self, session_id: Optional[str], delta_tokens: int, model_profile: Optional[str] = None) -> SessionRecord:
        if delta_tokens <= 0:
            raise ValueError("delta_tokens must be > 0")
        self.prune()
        resolved_session_id = session_id or str(uuid.uuid4())

        def operation(connection):
            now = time.time()
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (resolved_session_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO sessions (
                        session_id, total_tokens, model_profile, created_at,
                        last_updated, optimization_stats
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (resolved_session_id, 0, model_profile, now, now, None),
                )
                created_at = now
                current_total = 0
                current_profile = model_profile
                optimization_stats = {}
            else:
                created_at = row["created_at"]
                current_total = row["total_tokens"]
                current_profile = row["model_profile"]
                optimization_stats = self._decode_stats(row["optimization_stats"])

            new_total = current_total + delta_tokens
            resolved_profile = model_profile or current_profile
            connection.execute(
                """
                UPDATE sessions
                SET total_tokens = ?, model_profile = ?, last_updated = ?
                WHERE session_id = ?
                """,
                (new_total, resolved_profile, now, resolved_session_id),
            )
            return SessionRecord(
                session_id=resolved_session_id,
                total_tokens=new_total,
                model_profile=resolved_profile,
                created_at=created_at,
                last_updated=now,
                optimization_stats=optimization_stats,
            )

        return self._db.run_transaction(operation)

    def record_event(
        self,
        session_id: str,
        event_id: str,
        role: str,
        token_count: int,
        content_hash: str,
        model_profile: Optional[str] = None,
    ) -> LedgerWriteResult:
        if not session_id or not event_id:
            raise ValueError("session_id and event_id are required")
        if role not in {"user", "assistant"}:
            raise ValueError("role must be user or assistant")
        if token_count < 0:
            raise ValueError("token_count must be >= 0")
        if not content_hash:
            raise ValueError("content_hash is required")
        self.prune()

        def operation(connection):
            now = time.time()
            session_row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if session_row is None:
                connection.execute(
                    """
                    INSERT INTO sessions (
                        session_id, total_tokens, model_profile, created_at,
                        last_updated, optimization_stats
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (session_id, 0, model_profile, now, now, None),
                )
                session_created_at = now
                session_total = 0
                session_profile = model_profile
                optimization_stats = {}
            else:
                session_created_at = session_row["created_at"]
                session_total = session_row["total_tokens"]
                session_profile = session_row["model_profile"]
                optimization_stats = self._decode_stats(
                    session_row["optimization_stats"]
                )

            event_row = connection.execute(
                """
                SELECT * FROM conversation_events
                WHERE session_id = ? AND event_id = ?
                """,
                (session_id, event_id),
            ).fetchone()

            if event_row is None:
                status = "created"
                token_delta = token_count
                event_created_at = now
                event_updated_at = now
                connection.execute(
                    """
                    INSERT INTO conversation_events (
                        session_id, event_id, role, token_count, content_hash,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        event_id,
                        role,
                        token_count,
                        content_hash,
                        event_created_at,
                        event_updated_at,
                    ),
                )
            else:
                if event_row["role"] != role:
                    raise ValueError("event role cannot change")
                event_created_at = event_row["created_at"]
                if (
                    event_row["content_hash"] == content_hash
                    and event_row["token_count"] == token_count
                ):
                    status = "unchanged"
                    token_delta = 0
                    event_updated_at = event_row["updated_at"]
                else:
                    status = "updated"
                    token_delta = token_count - event_row["token_count"]
                    event_updated_at = now
                    connection.execute(
                        """
                        UPDATE conversation_events
                        SET token_count = ?, content_hash = ?, updated_at = ?
                        WHERE session_id = ? AND event_id = ?
                        """,
                        (
                            token_count,
                            content_hash,
                            event_updated_at,
                            session_id,
                            event_id,
                        ),
                    )

            corrected_total = max(session_total + token_delta, 0)
            resolved_profile = model_profile or session_profile
            connection.execute(
                """
                UPDATE sessions
                SET total_tokens = ?, model_profile = ?, last_updated = ?
                WHERE session_id = ?
                """,
                (corrected_total, resolved_profile, now, session_id),
            )
            event = ConversationEventRecord(
                session_id=session_id,
                event_id=event_id,
                role=role,
                token_count=token_count,
                content_hash=content_hash,
                created_at=event_created_at,
                updated_at=event_updated_at,
            )
            session = SessionRecord(
                session_id=session_id,
                total_tokens=corrected_total,
                model_profile=resolved_profile,
                created_at=session_created_at,
                last_updated=now,
                optimization_stats=optimization_stats,
            )
            return LedgerWriteResult(status=status, event=event, session=session)

        return self._db.run_transaction(operation)

    def get_event(
        self, session_id: str, event_id: str
    ) -> Optional[ConversationEventRecord]:
        row = self._db.fetch_one(
            """
            SELECT * FROM conversation_events
            WHERE session_id = ? AND event_id = ?
            """,
            (session_id, event_id),
        )
        return self._row_to_event(row) if row is not None else None

    def list_events(self, session_id: str) -> List[ConversationEventRecord]:
        rows = self._db.fetch_all(
            """
            SELECT * FROM conversation_events
            WHERE session_id = ?
            ORDER BY created_at, event_id
            """,
            (session_id,),
        )
        return [self._row_to_event(row) for row in rows]

    def reset_session(self, session_id: str, model_profile: Optional[str] = None) -> SessionRecord:
        self.prune()

        def operation(connection):
            now = time.time()
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO sessions (
                        session_id, total_tokens, model_profile, created_at,
                        last_updated, optimization_stats
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (session_id, 0, model_profile, now, now, None),
                )
                created_at = now
                current_profile = model_profile
                optimization_stats = {}
            else:
                created_at = row["created_at"]
                current_profile = row["model_profile"]
                optimization_stats = self._decode_stats(row["optimization_stats"])
                connection.execute(
                    "DELETE FROM conversation_events WHERE session_id = ?",
                    (session_id,),
                )
                connection.execute(
                    """
                    UPDATE sessions
                    SET total_tokens = 0, model_profile = ?, last_updated = ?
                    WHERE session_id = ?
                    """,
                    (model_profile or current_profile, now, session_id),
                )
            return SessionRecord(
                session_id=session_id,
                total_tokens=0,
                model_profile=model_profile or current_profile,
                created_at=created_at,
                last_updated=now,
                optimization_stats=optimization_stats,
            )

        return self._db.run_transaction(operation)

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
    def _decode_stats(payload) -> Dict[str, Any]:
        if not payload:
            return {}
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _row_to_record(row) -> SessionRecord:
        return SessionRecord(
            session_id=row["session_id"],
            total_tokens=row["total_tokens"],
            model_profile=row["model_profile"],
            created_at=row["created_at"],
            last_updated=row["last_updated"],
            optimization_stats=SessionStore._decode_stats(row["optimization_stats"]),
        )

    @staticmethod
    def _row_to_event(row) -> ConversationEventRecord:
        return ConversationEventRecord(
            session_id=row["session_id"],
            event_id=row["event_id"],
            role=row["role"],
            token_count=row["token_count"],
            content_hash=row["content_hash"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
