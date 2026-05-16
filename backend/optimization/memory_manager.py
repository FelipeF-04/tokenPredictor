import time
from typing import Dict, Iterable, List, Optional

from .models import Chunk, MemorySnapshot, SessionState, TraceEvent


class SessionStore:
    def __init__(self, ttl_seconds: int = 7200) -> None:
        self._sessions: Dict[str, SessionState] = {}
        self._ttl_seconds = ttl_seconds

    def get_or_create(self, session_id: str) -> SessionState:
        self.prune()
        session = self._sessions.get(session_id)
        if session is None:
            session = SessionState(session_id=session_id)
            self._sessions[session_id] = session
        session.last_updated = time.time()
        return session

    def update_chunks(self, session: SessionState, chunks: Iterable[Chunk]) -> None:
        for chunk in chunks:
            session.chunks[chunk.chunk_id] = chunk
        session.last_updated = time.time()

    def update_instructions(self, session: SessionState, instructions: Iterable) -> None:
        for instruction in instructions:
            session.instructions[instruction.instruction_id] = instruction
        session.last_updated = time.time()

    def get(self, session_id: str) -> Optional[SessionState]:
        return self._sessions.get(session_id)

    def prune(self) -> None:
        if self._ttl_seconds <= 0:
            return
        cutoff = time.time() - self._ttl_seconds
        stale = [sid for sid, sess in self._sessions.items() if sess.last_updated < cutoff]
        for sid in stale:
            self._sessions.pop(sid, None)


class MemoryManager:
    def assign_tiers(
        self,
        chunks: List[Chunk],
        budget_tokens: int,
        trace_events: List[TraceEvent],
        strategy_name: str,
    ) -> MemorySnapshot:
        active: List[Chunk] = []
        summarized: List[Chunk] = []
        archived: List[Chunk] = []

        tokens_used = 0
        ranked = sorted(
            [chunk for chunk in chunks if not chunk.removed],
            key=lambda item: (-item.relevance_score, item.index, item.chunk_id),
        )

        for chunk in ranked:
            if tokens_used + chunk.tokens <= budget_tokens:
                chunk.memory_tier = "active"
                active.append(chunk)
                tokens_used += chunk.tokens
                trace_events.append(
                    TraceEvent(
                        stage="memory",
                        action="tiered",
                        item_id=chunk.chunk_id,
                        reason="kept in active memory",
                        scores={"relevance": chunk.relevance_score},
                        token_delta=0,
                        strategy=strategy_name,
                    )
                )
                continue

            chunk.memory_tier = "archived"
            archived.append(chunk)
            trace_events.append(
                TraceEvent(
                    stage="memory",
                    action="tiered",
                    item_id=chunk.chunk_id,
                    reason="moved to archived memory",
                    scores={"relevance": chunk.relevance_score},
                    token_delta=0,
                    strategy=strategy_name,
                )
            )

        return MemorySnapshot(active=active, summarized=summarized, archived=archived)
