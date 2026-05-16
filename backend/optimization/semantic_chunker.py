import hashlib
import re
from typing import List

from tokenizer import count_tokens
from .models import Chunk, Message


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _stable_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _split_sentences(text: str) -> List[str]:
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    return sentences if sentences else [text]


class SemanticChunker:
    def __init__(self, max_tokens: int = 350, overlap_tokens: int = 40) -> None:
        self.max_tokens = max_tokens
        self.overlap_tokens = max(0, overlap_tokens)

    def chunk_messages(self, messages: List[Message]) -> List[Chunk]:
        chunks: List[Chunk] = []
        global_index = 0
        for index, message in enumerate(messages):
            message_id = message.message_id or f"msg_{index}"
            segments = self._split_message(message.content)
            for segment_index, segment in enumerate(segments):
                segment_text = segment.strip()
                if not segment_text:
                    continue
                tokens = count_tokens(segment_text)
                chunk_id = _stable_hash(
                    f"{message_id}:{message.role}:{segment_index}:{segment_text}"
                )
                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        text=segment_text,
                        role=message.role,
                        message_id=message_id,
                        index=global_index,
                        tokens=tokens,
                        embedding_key="",
                    )
                )
                global_index += 1
        return chunks

    def _split_message(self, text: str) -> List[str]:
        if count_tokens(text) <= self.max_tokens:
            return [text]

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text]

        chunks: List[str] = []
        current: List[str] = []
        current_tokens = 0

        def flush_current() -> None:
            nonlocal current, current_tokens
            if current:
                chunks.append(" ".join(current).strip())
            current = []
            current_tokens = 0

        for paragraph in paragraphs:
            paragraph_tokens = count_tokens(paragraph)
            if paragraph_tokens > self.max_tokens:
                sentences = _split_sentences(paragraph)
                for sentence in sentences:
                    sentence_tokens = count_tokens(sentence)
                    if current_tokens + sentence_tokens > self.max_tokens:
                        flush_current()
                    current.append(sentence)
                    current_tokens += sentence_tokens
            else:
                if current_tokens + paragraph_tokens > self.max_tokens:
                    flush_current()
                current.append(paragraph)
                current_tokens += paragraph_tokens

        flush_current()

        if self.overlap_tokens <= 0 or len(chunks) <= 1:
            return chunks

        overlapped: List[str] = []
        for chunk in chunks:
            if not overlapped:
                overlapped.append(chunk)
                continue
            previous = overlapped[-1]
            overlap = self._collect_overlap(previous)
            if overlap:
                overlapped.append(f"{overlap} {chunk}".strip())
            else:
                overlapped.append(chunk)
        return overlapped

    def _collect_overlap(self, text: str) -> str:
        if self.overlap_tokens <= 0:
            return ""
        sentences = _split_sentences(text)
        collected: List[str] = []
        tokens = 0
        for sentence in reversed(sentences):
            sentence_tokens = count_tokens(sentence)
            if tokens + sentence_tokens > self.overlap_tokens and collected:
                break
            collected.append(sentence)
            tokens += sentence_tokens
            if tokens >= self.overlap_tokens:
                break
        return " ".join(reversed(collected)).strip()
