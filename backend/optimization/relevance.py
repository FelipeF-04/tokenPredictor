import re
from typing import Dict, Iterable, List, Tuple

from .models import Chunk, TraceEvent


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def _lexical_score(query: str, text: str) -> float:
    query_tokens = set(_tokenize(query))
    text_tokens = set(_tokenize(text))
    if not query_tokens or not text_tokens:
        return 0.0
    overlap = query_tokens.intersection(text_tokens)
    return len(overlap) / max(len(query_tokens.union(text_tokens)), 1)


def score_chunks_embedding(
    query_embedding: List[float],
    chunks: Iterable[Chunk],
    embeddings: Dict[str, List[float]],
    trace_events: List[TraceEvent],
) -> None:
    if not query_embedding:
        return
    for chunk in chunks:
        embedding = embeddings.get(chunk.embedding_key)
        if not embedding:
            continue
        similarity = float(sum(a * b for a, b in zip(query_embedding, embedding)))
        chunk.relevance_score = similarity
        trace_events.append(
            TraceEvent(
                stage="relevance",
                action="scored",
                item_id=chunk.chunk_id,
                reason="embedding similarity",
                scores={"relevance": similarity},
                token_delta=0,
            )
        )


def score_chunks_lexical(
    query_text: str,
    chunks: Iterable[Chunk],
    trace_events: List[TraceEvent],
) -> None:
    for chunk in chunks:
        score = _lexical_score(query_text, chunk.text)
        chunk.relevance_score = score
        trace_events.append(
            TraceEvent(
                stage="relevance",
                action="scored",
                item_id=chunk.chunk_id,
                reason="lexical similarity",
                scores={"relevance": score},
                token_delta=0,
            )
        )


def score_chunks_hybrid(
    query_text: str,
    query_embedding: List[float],
    chunks: Iterable[Chunk],
    embeddings: Dict[str, List[float]],
    trace_events: List[TraceEvent],
    embedding_weight: float = 0.75,
) -> None:
    if not query_embedding:
        return score_chunks_lexical(query_text, chunks, trace_events)
    for chunk in chunks:
        embedding = embeddings.get(chunk.embedding_key)
        if not embedding:
            continue
        embedding_score = float(sum(a * b for a, b in zip(query_embedding, embedding)))
        lexical_score = _lexical_score(query_text, chunk.text)
        score = embedding_weight * embedding_score + (1 - embedding_weight) * lexical_score
        chunk.relevance_score = score
        trace_events.append(
            TraceEvent(
                stage="relevance",
                action="scored",
                item_id=chunk.chunk_id,
                reason="hybrid similarity",
                scores={"relevance": score, "embedding": embedding_score, "lexical": lexical_score},
                token_delta=0,
            )
        )
