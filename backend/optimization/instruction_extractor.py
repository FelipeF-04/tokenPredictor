import hashlib
import re
from typing import Iterable, List, Tuple

from tokenizer import count_tokens
from .embeddings import EmbeddingCache, EmbeddingProvider, hash_text, make_embedding_key
from .models import Instruction, TraceEvent


_INSTRUCTION_CUES = (
    "must",
    "should",
    "do not",
    "don't",
    "never",
    "always",
    "avoid",
    "required",
    "require",
    "keep",
    "no ",
    "only ",
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _normalize(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return normalized.rstrip(".!")


def _stable_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _split_sentences(text: str) -> List[str]:
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    return sentences if sentences else [text]


def _looks_like_instruction(sentence: str) -> bool:
    lowered = sentence.lower().strip()
    if len(lowered) < 6:
        return False
    return any(cue in lowered for cue in _INSTRUCTION_CUES)


def _instruction_score(text: str, source_count: int) -> float:
    length_boost = min(len(text) / 200.0, 0.4)
    source_boost = min(source_count * 0.15, 0.45)
    return min(1.0, 0.25 + length_boost + source_boost)


class InstructionExtractor:
    def __init__(
        self,
        provider: EmbeddingProvider,
        cache: EmbeddingCache,
        similarity_threshold: float = 0.9,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.similarity_threshold = similarity_threshold

    def extract(
        self, chunks: Iterable[Tuple[str, str]], trace_events: List[TraceEvent]
    ) -> List[Instruction]:
        candidates: List[Tuple[str, str, str]] = []
        for chunk_id, text in chunks:
            for sentence in _split_sentences(text):
                if _looks_like_instruction(sentence):
                    normalized = _normalize(sentence)
                    candidates.append((chunk_id, sentence.strip(), normalized))

        if not candidates:
            return []

        texts = [item[1] for item in candidates]
        embeddings = self._embed_texts(texts)

        instructions: List[Instruction] = []
        for idx, (chunk_id, text, normalized) in enumerate(candidates):
            embedding = embeddings[idx]
            merged = False
            for existing in instructions:
                existing_embedding = self.cache.get(existing.embedding_key or "")
                if not existing_embedding:
                    continue
                similarity = float(sum(a * b for a, b in zip(embedding, existing_embedding)))
                if similarity >= self.similarity_threshold:
                    existing.source_chunk_ids.append(chunk_id)
                    existing.score = _instruction_score(existing.text, len(existing.source_chunk_ids))
                    if len(text) > len(existing.text):
                        existing.text = text
                        existing.normalized = normalized
                    trace_events.append(
                        TraceEvent(
                            stage="instruction_extraction",
                            action="merged",
                            item_id=existing.instruction_id,
                            reason="similar instruction merged",
                            scores={"similarity": similarity},
                            token_delta=0,
                        )
                    )
                    merged = True
                    break
            if merged:
                continue

            instruction_id = _stable_hash(normalized)
            instruction = Instruction(
                instruction_id=instruction_id,
                text=text,
                normalized=normalized,
                source_chunk_ids=[chunk_id],
                score=_instruction_score(text, 1),
                embedding_key=make_embedding_key(
                    self.provider.name, self.provider.model_name, hash_text(text)
                ),
            )
            trace_events.append(
                TraceEvent(
                    stage="instruction_extraction",
                    action="extracted",
                    item_id=instruction_id,
                    reason="instruction cue detected",
                    scores={"score": instruction.score},
                    token_delta=count_tokens(text),
                )
            )
            instructions.append(instruction)

        instructions.sort(key=lambda item: (-item.score, item.instruction_id))
        return instructions

    def render_instructions(self, instructions: List[Instruction], budget_tokens: int) -> str:
        if budget_tokens <= 0 or not instructions:
            return ""
        rendered: List[str] = []
        tokens_used = 0
        for instruction in instructions:
            line = f"- {instruction.text.strip()}"
            line_tokens = count_tokens(line)
            if tokens_used + line_tokens > budget_tokens and rendered:
                break
            if line_tokens > budget_tokens and not rendered:
                break
            rendered.append(line)
            tokens_used += line_tokens
        if not rendered:
            return ""
        return "Persistent constraints:\n" + "\n".join(rendered)

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        embeddings: List[List[float]] = []
        missing: List[str] = []
        missing_indices: List[int] = []
        for idx, text in enumerate(texts):
            key = make_embedding_key(
                self.provider.name, self.provider.model_name, hash_text(text)
            )
            cached = self.cache.get(key)
            if cached is None:
                missing.append(text)
                missing_indices.append(idx)
                embeddings.append([])
            else:
                embeddings.append(cached)
        if missing:
            computed = self.provider.embed_texts(missing)
            for offset, vector in enumerate(computed):
                idx = missing_indices[offset]
                key = make_embedding_key(
                    self.provider.name, self.provider.model_name, hash_text(texts[idx])
                )
                self.cache.set(key, vector)
                embeddings[idx] = vector
        return embeddings
