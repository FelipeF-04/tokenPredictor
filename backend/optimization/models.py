from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time


@dataclass
class ModelProfile:
    name: str
    context_window: int
    max_output_tokens: int
    system_ratio: float
    instruction_ratio: float
    memory_ratio: float
    retrieval_ratio: float
    compression_tolerance: float
    tokenizer: str = "cl100k_base"


@dataclass
class PipelineConfig:
    max_chunk_tokens: int = 350
    chunk_overlap_tokens: int = 40
    dedup_threshold: float = 0.92
    instruction_similarity_threshold: float = 0.9
    min_relevance: float = 0.2
    trace_enabled: bool = True
    deterministic: bool = True
    max_instructions: int = 40


@dataclass
class Message:
    role: str
    content: str
    message_id: str
    timestamp: Optional[str] = None


@dataclass
class Chunk:
    chunk_id: str
    text: str
    role: str
    message_id: str
    index: int
    tokens: int
    embedding_key: str
    dedup_score: float = 0.0
    relevance_score: float = 0.0
    memory_tier: str = "active"
    removed: bool = False
    removal_reason: Optional[str] = None


@dataclass
class ChunkSnapshot:
    chunk_id: str
    text: str
    role: str
    message_id: str
    tokens: int


@dataclass
class Instruction:
    instruction_id: str
    text: str
    normalized: str
    source_chunk_ids: List[str]
    score: float = 0.0
    embedding_key: Optional[str] = None


@dataclass
class MemorySnapshot:
    active: List[Chunk] = field(default_factory=list)
    summarized: List[Chunk] = field(default_factory=list)
    archived: List[Chunk] = field(default_factory=list)


@dataclass
class TokenBudget:
    total_available: int
    system_budget: int
    instruction_budget: int
    memory_budget: int
    retrieval_budget: int
    output_budget: int
    conversation_budget: int


@dataclass
class TraceEvent:
    stage: str
    action: str
    item_id: Optional[str]
    reason: str
    scores: Dict[str, float] = field(default_factory=dict)
    token_delta: int = 0
    strategy: Optional[str] = None


@dataclass
class OptimizationTrace:
    session_id: str
    strategy: str
    events: List[TraceEvent] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OptimizationMetrics:
    original_tokens: int
    optimized_tokens: int
    token_reduction: int
    token_reduction_pct: float
    semantic_preservation: float
    instruction_preservation: float
    reasoning_preservation: float
    code_preservation: float
    hallucination_risk: float
    confidence: float


@dataclass
class SessionState:
    session_id: str
    chunks: Dict[str, Chunk] = field(default_factory=dict)
    instructions: Dict[str, Instruction] = field(default_factory=dict)
    embeddings: Dict[str, List[float]] = field(default_factory=dict)
    message_hashes: Dict[str, str] = field(default_factory=dict)
    message_chunks: Dict[str, List[ChunkSnapshot]] = field(default_factory=dict)
    last_updated: float = field(default_factory=lambda: time.time())


def default_model_profiles() -> Dict[str, ModelProfile]:
    return {
        "gpt-4o-mini": ModelProfile(
            name="gpt-4o-mini",
            context_window=128000,
            max_output_tokens=2048,
            system_ratio=0.01,
            instruction_ratio=0.02,
            memory_ratio=0.25,
            retrieval_ratio=0.05,
            compression_tolerance=0.45,
        ),
        "gpt-4.1": ModelProfile(
            name="gpt-4.1",
            context_window=128000,
            max_output_tokens=3072,
            system_ratio=0.01,
            instruction_ratio=0.02,
            memory_ratio=0.3,
            retrieval_ratio=0.05,
            compression_tolerance=0.4,
        ),
        "gpt-5": ModelProfile(
            name="gpt-5",
            context_window=256000,
            max_output_tokens=4096,
            system_ratio=0.008,
            instruction_ratio=0.015,
            memory_ratio=0.32,
            retrieval_ratio=0.05,
            compression_tolerance=0.35,
        ),
        "local-8k": ModelProfile(
            name="local-8k",
            context_window=8192,
            max_output_tokens=1024,
            system_ratio=0.02,
            instruction_ratio=0.05,
            memory_ratio=0.3,
            retrieval_ratio=0.05,
            compression_tolerance=0.25,
        ),
        "local-16k": ModelProfile(
            name="local-16k",
            context_window=16384,
            max_output_tokens=1536,
            system_ratio=0.015,
            instruction_ratio=0.04,
            memory_ratio=0.32,
            retrieval_ratio=0.05,
            compression_tolerance=0.3,
        ),
    }


def chunk_to_dict(chunk: Chunk) -> Dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "text": chunk.text,
        "role": chunk.role,
        "message_id": chunk.message_id,
        "index": chunk.index,
        "tokens": chunk.tokens,
        "dedup_score": chunk.dedup_score,
        "relevance_score": chunk.relevance_score,
        "memory_tier": chunk.memory_tier,
        "removed": chunk.removed,
        "removal_reason": chunk.removal_reason,
    }


def instruction_to_dict(instruction: Instruction) -> Dict[str, Any]:
    return {
        "instruction_id": instruction.instruction_id,
        "text": instruction.text,
        "normalized": instruction.normalized,
        "source_chunk_ids": instruction.source_chunk_ids,
        "score": instruction.score,
    }


def memory_snapshot_to_dict(snapshot: MemorySnapshot) -> Dict[str, Any]:
    return {
        "active": [chunk_to_dict(chunk) for chunk in snapshot.active],
        "summarized": [chunk_to_dict(chunk) for chunk in snapshot.summarized],
        "archived": [chunk_to_dict(chunk) for chunk in snapshot.archived],
    }


def trace_to_dict(trace: OptimizationTrace) -> Dict[str, Any]:
    return {
        "session_id": trace.session_id,
        "strategy": trace.strategy,
        "summary": trace.summary,
        "events": [
            {
                "stage": event.stage,
                "action": event.action,
                "item_id": event.item_id,
                "reason": event.reason,
                "scores": event.scores,
                "token_delta": event.token_delta,
                "strategy": event.strategy,
            }
            for event in trace.events
        ],
    }


def budget_to_dict(budget: TokenBudget) -> Dict[str, Any]:
    return {
        "total_available": budget.total_available,
        "system_budget": budget.system_budget,
        "instruction_budget": budget.instruction_budget,
        "memory_budget": budget.memory_budget,
        "retrieval_budget": budget.retrieval_budget,
        "output_budget": budget.output_budget,
        "conversation_budget": budget.conversation_budget,
    }


def metrics_to_dict(metrics: OptimizationMetrics) -> Dict[str, Any]:
    return {
        "original_tokens": metrics.original_tokens,
        "optimized_tokens": metrics.optimized_tokens,
        "token_reduction": metrics.token_reduction,
        "token_reduction_pct": metrics.token_reduction_pct,
        "semantic_preservation": metrics.semantic_preservation,
        "instruction_preservation": metrics.instruction_preservation,
        "reasoning_preservation": metrics.reasoning_preservation,
        "code_preservation": metrics.code_preservation,
        "hallucination_risk": metrics.hallucination_risk,
        "confidence": metrics.confidence,
    }
