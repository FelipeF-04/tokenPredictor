from dataclasses import dataclass
from typing import Dict, List, Tuple

from ..embeddings import hash_text
from ..models import Chunk, ChunkSnapshot, Message, SessionState
from ..semantic_chunker import SemanticChunker


@dataclass
class ChunkReuseStats:
    messages_reused: int = 0
    messages_total: int = 0
    chunks_reused: int = 0
    chunks_total: int = 0

    def message_reuse_rate(self) -> float:
        if self.messages_total == 0:
            return 0.0
        return self.messages_reused / self.messages_total

    def chunk_reuse_rate(self) -> float:
        if self.chunks_total == 0:
            return 0.0
        return self.chunks_reused / self.chunks_total


def snapshot_chunks(chunks: List[Chunk]) -> List[ChunkSnapshot]:
    return [
        ChunkSnapshot(
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            role=chunk.role,
            message_id=chunk.message_id,
            tokens=chunk.tokens,
        )
        for chunk in chunks
    ]


def restore_chunks(snapshots: List[ChunkSnapshot]) -> List[Chunk]:
    return [
        Chunk(
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            role=chunk.role,
            message_id=chunk.message_id,
            index=0,
            tokens=chunk.tokens,
            embedding_key="",
        )
        for chunk in snapshots
    ]


class IncrementalChunker:
    def __init__(self, chunker: SemanticChunker) -> None:
        self._chunker = chunker

    def build_chunks(self, session: SessionState, messages: List[Message]) -> Tuple[List[Chunk], ChunkReuseStats]:
        stats = ChunkReuseStats(messages_total=len(messages))
        chunks: List[Chunk] = []
        seen_message_ids = set()

        for message in messages:
            seen_message_ids.add(message.message_id)
            message_hash = hash_text(f"{message.role}:{message.content}")
            cached_hash = session.message_hashes.get(message.message_id)
            if cached_hash == message_hash:
                cached_chunks = session.message_chunks.get(message.message_id)
                if cached_chunks:
                    stats.messages_reused += 1
                    stats.chunks_reused += len(cached_chunks)
                    chunks.extend(restore_chunks(cached_chunks))
                    continue

            new_chunks = self._chunker.chunk_messages([message])
            session.message_hashes[message.message_id] = message_hash
            session.message_chunks[message.message_id] = snapshot_chunks(new_chunks)
            chunks.extend(new_chunks)

        stale_ids = [mid for mid in session.message_hashes.keys() if mid not in seen_message_ids]
        for message_id in stale_ids:
            session.message_hashes.pop(message_id, None)
            session.message_chunks.pop(message_id, None)

        stats.chunks_total = len(chunks)
        for idx, chunk in enumerate(chunks):
            chunk.index = idx
        return chunks, stats
