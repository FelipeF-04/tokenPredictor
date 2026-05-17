import uuid
from typing import Any, Dict, List, Optional

from tokenizer import count_tokens

from .budget_manager import compute_budget
from .compression import select_chunks_for_budget
from .deduplication import deduplicate_chunks
from .embeddings import EmbeddingCache, EmbeddingProviderFactory, make_embedding_key
from .instruction_extractor import InstructionExtractor
from .memory_manager import MemoryManager, SessionStore
from .models import (
    Chunk,
    Message,
    OptimizationTrace,
    PipelineConfig,
    TokenBudget,
    TraceEvent,
    chunk_to_dict,
    budget_to_dict,
    default_model_profiles,
    instruction_to_dict,
    memory_snapshot_to_dict,
    metrics_to_dict,
    trace_to_dict,
)
from .optimizer_metrics import build_metrics
from .relevance import score_chunks_embedding, score_chunks_hybrid, score_chunks_lexical
from .semantic_chunker import SemanticChunker
from .strategies import auto_strategy, get_strategy
from .validator import validate_preservation


class OptimizationPipeline:
    def __init__(
        self,
        session_store: Optional[SessionStore] = None,
        embedding_cache: Optional[EmbeddingCache] = None,
        config: Optional[PipelineConfig] = None,
    ) -> None:
        self.session_store = session_store or SessionStore()
        self.embedding_cache = embedding_cache or EmbeddingCache()
        self.config = config or PipelineConfig()
        self.chunker = SemanticChunker(
            max_tokens=self.config.max_chunk_tokens,
            overlap_tokens=self.config.chunk_overlap_tokens,
        )
        self.memory_manager = MemoryManager()
        self.model_profiles = default_model_profiles()

    def optimize(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        messages = self._parse_messages(payload.get("messages"))
        if not messages:
            raise ValueError("messages must be a non-empty list")

        session_id = str(payload.get("session_id") or uuid.uuid4())
        model_profile_name = payload.get("model_profile", "gpt-4o-mini")
        strategy_name = payload.get("strategy", "auto")
        retrieval_mode = payload.get("retrieval_mode", "embedding")
        options = payload.get("options", {})
        query_text = payload.get("query") or self._infer_query(messages)

        embedding_provider_name = payload.get("embedding_provider", "sentence-transformers")
        embedding_model_name = payload.get("embedding_model", "bge-small-en")

        profile = self.model_profiles.get(model_profile_name)
        if not profile:
            raise ValueError(f"Unknown model_profile: {model_profile_name}")

        session = self.session_store.get_or_create(session_id)
        trace = OptimizationTrace(session_id=session_id, strategy=strategy_name)

        chunks = self.chunker.chunk_messages(messages)
        self.session_store.update_chunks(session, chunks)

        provider = EmbeddingProviderFactory.get_provider(
            embedding_provider_name, embedding_model_name, self.config.deterministic
        )
        embeddings = self._embed_chunks(provider, session, chunks)

        instruction_extractor = InstructionExtractor(
            provider,
            self.embedding_cache,
            similarity_threshold=self.config.instruction_similarity_threshold,
        )
        chunk_tuples = [(chunk.chunk_id, chunk.text) for chunk in chunks]
        instructions = instruction_extractor.extract(chunk_tuples, trace.events)
        self.session_store.update_instructions(session, instructions)

        query_embedding = self._embed_query(provider, query_text, session)
        if retrieval_mode == "lexical":
            score_chunks_lexical(query_text, chunks, trace.events)
        elif retrieval_mode == "hybrid":
            score_chunks_hybrid(query_text, query_embedding, chunks, embeddings, trace.events)
        else:
            score_chunks_embedding(query_embedding, chunks, embeddings, trace.events)

        budget = compute_budget(profile, options)
        budget_pressure = self._estimate_budget_pressure(chunks, budget)
        if strategy_name == "auto":
            strategy = auto_strategy(budget_pressure)
            trace.strategy = strategy.name
            trace.events.append(
                TraceEvent(
                    stage="strategy",
                    action="selected",
                    item_id=strategy.name,
                    reason="auto-selected by budget pressure",
                    scores={"budget_pressure": budget_pressure},
                    token_delta=0,
                    strategy=strategy.name,
                )
            )
        else:
            strategy = get_strategy(strategy_name)
            trace.strategy = strategy.name
            trace.events.append(
                TraceEvent(
                    stage="strategy",
                    action="selected",
                    item_id=strategy.name,
                    reason="requested strategy",
                    scores={"budget_pressure": budget_pressure},
                    token_delta=0,
                    strategy=strategy.name,
                )
            )

        trace.events.append(
            TraceEvent(
                stage="budget",
                action="allocated",
                item_id=None,
                reason="profile budget allocation",
                scores={
                    "total_available": float(budget.total_available),
                    "conversation_budget": float(budget.conversation_budget),
                },
                token_delta=0,
                strategy=strategy.name,
            )
        )

        dedup_threshold = min(strategy.dedup_threshold, self.config.dedup_threshold)
        kept_chunks, _removed_chunks = deduplicate_chunks(
            chunks, embeddings, dedup_threshold, trace.events, strategy.name
        )

        memory_snapshot = self.memory_manager.assign_tiers(
            kept_chunks, budget.memory_budget, trace.events, strategy.name
        )

        selected_chunks = select_chunks_for_budget(
            memory_snapshot.active, budget.conversation_budget, strategy.min_relevance, trace.events, strategy.name
        )

        included_instruction_ids = self._select_instructions(
            instructions, budget.instruction_budget
        )
        instruction_text = instruction_extractor.render_instructions(
            [ins for ins in instructions if ins.instruction_id in included_instruction_ids],
            budget.instruction_budget,
        )
        instruction_tokens = count_tokens(instruction_text) if instruction_text else 0
        trace.events.append(
            TraceEvent(
                stage="instructions",
                action="selected",
                item_id=None,
                reason="instruction budget applied",
                scores={
                    "instructions_total": float(len(instructions)),
                    "instructions_included": float(len(included_instruction_ids)),
                },
                token_delta=instruction_tokens,
                strategy=strategy.name,
            )
        )

        rendered_prompt = self._render_prompt(instruction_text, selected_chunks)

        original_tokens = sum(chunk.tokens for chunk in chunks)
        optimized_tokens = sum(chunk.tokens for chunk in selected_chunks) + instruction_tokens

        validation = validate_preservation(
            chunks,
            selected_chunks,
            instructions,
            included_instruction_ids,
            embeddings,
        )
        metrics = build_metrics(original_tokens, optimized_tokens, validation)

        trace.summary = {
            "original_tokens": original_tokens,
            "optimized_tokens": optimized_tokens,
            "budget": budget_to_dict(budget),
            "budget_pressure": budget_pressure,
            "strategy": strategy.name,
            "retrieval_mode": retrieval_mode,
            "embedding_model": provider.model_name,
        }

        response = {
            "session_id": session_id,
            "model_profile": profile.name,
            "strategy": strategy.name,
            "deterministic": self.config.deterministic,
            "stats": {
                "total_chunks": len(chunks),
                "kept_chunks": len(selected_chunks),
                "removed_chunks": sum(1 for chunk in chunks if chunk.removed),
            },
            "optimized": {
                "instructions": [
                    {
                        **instruction_to_dict(instruction),
                        "included": instruction.instruction_id in included_instruction_ids,
                    }
                    for instruction in instructions
                ],
                "messages": [chunk_to_dict(chunk) for chunk in selected_chunks],
                "rendered_prompt": rendered_prompt,
                "token_counts": {
                    "original": original_tokens,
                    "optimized": optimized_tokens,
                    "instruction_tokens": instruction_tokens,
                },
            },
            "memory": memory_snapshot_to_dict(memory_snapshot),
            "metrics": metrics_to_dict(metrics),
        }

        if options.get("include_trace", True):
            response["trace"] = trace_to_dict(trace)

        if options.get("include_removed_chunks", False):
            all_removed = [chunk for chunk in chunks if chunk.removed]
            response["removed_chunks"] = [chunk_to_dict(chunk) for chunk in all_removed]

        return response

    def _parse_messages(self, raw_messages: Any) -> List[Message]:
        if not isinstance(raw_messages, list):
            return []
        messages: List[Message] = []
        for idx, raw in enumerate(raw_messages):
            if not isinstance(raw, dict):
                continue
            role = str(raw.get("role", "user")).strip() or "user"
            content = str(raw.get("content", "")).strip()
            if not content:
                continue
            message_id = str(raw.get("message_id") or f"msg_{idx}")
            timestamp = raw.get("timestamp")
            messages.append(
                Message(role=role, content=content, message_id=message_id, timestamp=timestamp)
            )
        return messages

    def _infer_query(self, messages: List[Message]) -> str:
        for message in reversed(messages):
            if message.role == "user":
                return message.content
        return messages[-1].content if messages else ""

    def _embed_chunks(self, provider, session, chunks: List[Chunk]) -> Dict[str, List[float]]:
        embeddings: Dict[str, List[float]] = {}
        missing_texts: List[str] = []
        missing_keys: List[str] = []

        for chunk in chunks:
            key = make_embedding_key(provider.name, provider.model_name, chunk.text)
            chunk.embedding_key = key
            cached = self.embedding_cache.get(key) or session.embeddings.get(key)
            if cached is None:
                missing_texts.append(chunk.text)
                missing_keys.append(key)
            else:
                embeddings[key] = cached

        if missing_texts:
            computed = provider.embed_texts(missing_texts)
            for idx, vector in enumerate(computed):
                key = missing_keys[idx]
                self.embedding_cache.set(key, vector)
                session.embeddings[key] = vector
                embeddings[key] = vector

        return embeddings

    def _embed_query(self, provider, query_text: str, session) -> List[float]:
        if not query_text:
            return []
        key = make_embedding_key(provider.name, provider.model_name, query_text)
        cached = self.embedding_cache.get(key) or session.embeddings.get(key)
        if cached is not None:
            return cached
        embedding = provider.embed_texts([query_text])[0]
        self.embedding_cache.set(key, embedding)
        session.embeddings[key] = embedding
        return embedding

    def _select_instructions(self, instructions: List, budget_tokens: int) -> List[str]:
        included: List[str] = []
        tokens_used = 0
        for instruction in instructions:
            token_count = count_tokens(instruction.text)
            if token_count > budget_tokens and not included:
                break
            if tokens_used + token_count > budget_tokens and included:
                break
            included.append(instruction.instruction_id)
            tokens_used += token_count
        return included

    def _render_prompt(self, instruction_text: str, chunks: List[Chunk]) -> List[Dict[str, str]]:
        rendered: List[Dict[str, str]] = []
        if instruction_text:
            rendered.append({"role": "system", "content": instruction_text})
        ordered = sorted(chunks, key=lambda item: (item.index, item.chunk_id))
        for chunk in ordered:
            rendered.append({"role": chunk.role, "content": chunk.text})
        return rendered

    def _estimate_budget_pressure(self, chunks: List[Chunk], budget: TokenBudget) -> float:
        total_tokens = sum(chunk.tokens for chunk in chunks)
        if budget.total_available <= 0:
            return 1.0
        return min(total_tokens / budget.total_available, 1.0)
