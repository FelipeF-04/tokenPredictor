from typing import List

from .models import Chunk, TraceEvent


def select_chunks_for_budget(
    chunks: List[Chunk],
    budget_tokens: int,
    min_relevance: float,
    trace_events: List[TraceEvent],
    strategy_name: str,
) -> List[Chunk]:
    selected: List[Chunk] = []
    tokens_used = 0

    ranked = sorted(
        [chunk for chunk in chunks if not chunk.removed],
        key=lambda item: (-item.relevance_score, item.index, item.chunk_id),
    )

    for chunk in ranked:
        if chunk.relevance_score < min_relevance:
            chunk.removed = True
            chunk.removal_reason = "below relevance threshold"
            trace_events.append(
                TraceEvent(
                    stage="compression",
                    action="removed",
                    item_id=chunk.chunk_id,
                    reason="below relevance threshold",
                    scores={"relevance": chunk.relevance_score},
                    token_delta=-chunk.tokens,
                    strategy=strategy_name,
                )
            )
            continue

        if tokens_used + chunk.tokens > budget_tokens:
            chunk.removed = True
            chunk.removal_reason = "budget overflow"
            trace_events.append(
                TraceEvent(
                    stage="compression",
                    action="removed",
                    item_id=chunk.chunk_id,
                    reason="budget overflow",
                    scores={"relevance": chunk.relevance_score},
                    token_delta=-chunk.tokens,
                    strategy=strategy_name,
                )
            )
            continue

        selected.append(chunk)
        tokens_used += chunk.tokens
        trace_events.append(
            TraceEvent(
                stage="compression",
                action="kept",
                item_id=chunk.chunk_id,
                reason="within budget",
                scores={"relevance": chunk.relevance_score},
                token_delta=chunk.tokens,
                strategy=strategy_name,
            )
        )

    return selected
