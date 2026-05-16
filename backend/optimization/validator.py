import math
import re
from typing import Dict, Iterable, List, Optional

from .models import Chunk, Instruction


_CODE_PATTERN = re.compile(r"```|\b(class|def|function|import|return|const|let|var)\b")


def _mean_embedding(vectors: List[List[float]]) -> List[float]:
    if not vectors:
        return []
    dim = len(vectors[0])
    sums = [0.0] * dim
    for vector in vectors:
        for idx in range(dim):
            sums[idx] += vector[idx]
    mean = [value / len(vectors) for value in sums]
    norm = math.sqrt(sum(value * value for value in mean))
    if norm == 0:
        return mean
    return [value / norm for value in mean]


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))


def _contains_code(text: str) -> bool:
    return bool(_CODE_PATTERN.search(text))


def validate_preservation(
    original_chunks: Iterable[Chunk],
    optimized_chunks: Iterable[Chunk],
    instructions: List[Instruction],
    included_instruction_ids: List[str],
    embeddings: Dict[str, List[float]],
) -> Dict[str, float]:
    original_list = list(original_chunks)
    optimized_list = list(optimized_chunks)

    original_vectors = [
        embeddings.get(chunk.embedding_key)
        for chunk in original_list
        if embeddings.get(chunk.embedding_key)
    ]
    optimized_vectors = [
        embeddings.get(chunk.embedding_key)
        for chunk in optimized_list
        if embeddings.get(chunk.embedding_key)
    ]

    semantic_preservation = _cosine_similarity(
        _mean_embedding(original_vectors), _mean_embedding(optimized_vectors)
    )

    if not instructions:
        instruction_preservation = 1.0
    else:
        preserved = sum(
            1 for instruction in instructions if instruction.instruction_id in included_instruction_ids
        )
        instruction_preservation = preserved / max(len(instructions), 1)

    top_candidates = sorted(
        original_list, key=lambda item: (-item.relevance_score, item.index, item.chunk_id)
    )[:10]
    selected_ids = {chunk.chunk_id for chunk in optimized_list}
    if not top_candidates:
        reasoning_preservation = 1.0
    else:
        reasoning_preservation = sum(1 for chunk in top_candidates if chunk.chunk_id in selected_ids) / max(
            len(top_candidates), 1
        )

    code_chunks = [chunk for chunk in original_list if _contains_code(chunk.text)]
    if not code_chunks:
        code_preservation = 1.0
    else:
        preserved_code = sum(1 for chunk in code_chunks if chunk.chunk_id in selected_ids)
        code_preservation = preserved_code / max(len(code_chunks), 1)

    hallucination_risk = max(0.0, 1.0 - ((semantic_preservation + instruction_preservation) / 2.0))

    confidence = (
        semantic_preservation * 0.4
        + instruction_preservation * 0.3
        + reasoning_preservation * 0.2
        + code_preservation * 0.1
    )

    return {
        "semantic_preservation": semantic_preservation,
        "instruction_preservation": instruction_preservation,
        "reasoning_preservation": reasoning_preservation,
        "code_preservation": code_preservation,
        "hallucination_risk": hallucination_risk,
        "confidence": confidence,
    }
