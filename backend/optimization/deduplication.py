import re
from typing import Dict, List, Tuple

from .models import Chunk, TraceEvent


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def _info_density(text: str) -> float:
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    return len(set(tokens)) / max(len(tokens), 1)


def deduplicate_chunks(
    chunks: List[Chunk],
    embeddings: Dict[str, List[float]],
    threshold: float,
    trace_events: List[TraceEvent],
    strategy_name: str,
) -> Tuple[List[Chunk], List[Chunk]]:
    kept: List[Chunk] = []
    removed: List[Chunk] = []

    for chunk in chunks:
        if chunk.removed:
            removed.append(chunk)
            continue
        duplicate_of = None
        duplicate_score = 0.0
        for existing in kept:
            embedding = embeddings.get(chunk.embedding_key)
            existing_embedding = embeddings.get(existing.embedding_key)
            if not embedding or not existing_embedding:
                continue
            similarity = float(sum(a * b for a, b in zip(embedding, existing_embedding)))
            if similarity >= threshold:
                duplicate_of = existing
                duplicate_score = similarity
                break

        if duplicate_of is None:
            kept.append(chunk)
            continue

        chunk_density = _info_density(chunk.text)
        existing_density = _info_density(duplicate_of.text)
        if chunk_density > existing_density:
            duplicate_of.removed = True
            duplicate_of.removal_reason = "semantic duplicate"
            duplicate_of.dedup_score = duplicate_score
            removed.append(duplicate_of)
            kept.remove(duplicate_of)
            kept.append(chunk)
            trace_events.append(
                TraceEvent(
                    stage="deduplication",
                    action="removed",
                    item_id=duplicate_of.chunk_id,
                    reason="replaced by denser duplicate",
                    scores={"similarity": duplicate_score},
                    token_delta=-duplicate_of.tokens,
                    strategy=strategy_name,
                )
            )
            continue

        chunk.removed = True
        chunk.removal_reason = "semantic duplicate"
        chunk.dedup_score = duplicate_score
        removed.append(chunk)
        trace_events.append(
            TraceEvent(
                stage="deduplication",
                action="removed",
                item_id=chunk.chunk_id,
                reason="semantic duplicate",
                scores={"similarity": duplicate_score},
                token_delta=-chunk.tokens,
                strategy=strategy_name,
            )
        )

    return kept, removed
