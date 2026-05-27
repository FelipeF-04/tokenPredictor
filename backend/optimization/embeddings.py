import hashlib
import threading
from typing import Dict, Iterable, List

import numpy as np

from .cache.embedding_cache import EmbeddingCache, EmbeddingStore


_MODEL_NAME_ALIASES = {
    "bge-small-en": "BAAI/bge-small-en-v1.5",
    "all-minilm-l6-v2": "sentence-transformers/all-MiniLM-L6-v2",
}


def hash_text(text: str) -> str:
    payload = text.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def make_embedding_key(provider_name: str, model_name: str, text_hash: str) -> str:
    payload = f"{provider_name}:{model_name}:{text_hash}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class EmbeddingProvider:
    def __init__(self, name: str, model_name: str, deterministic: bool = True) -> None:
        self.name = name
        self.model_name = model_name
        self.deterministic = deterministic

    def embed_texts(self, texts: Iterable[str]) -> List[List[float]]:
        raise NotImplementedError


class SentenceTransformerProvider(EmbeddingProvider):
    def __init__(self, model_name: str, deterministic: bool = True) -> None:
        super().__init__("sentence-transformers", model_name, deterministic)
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("sentence-transformers is not installed") from exc

        if deterministic:
            try:
                import torch

                torch.manual_seed(0)
                torch.use_deterministic_algorithms(True)
            except Exception:
                pass

        self._model = SentenceTransformer(model_name)

    def embed_texts(self, texts: Iterable[str]) -> List[List[float]]:
        if not texts:
            return []
        embeddings = self._model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        if isinstance(embeddings, np.ndarray):
            return embeddings.astype(float).tolist()
        return [np.asarray(vector, dtype=float).tolist() for vector in embeddings]


class EmbeddingProviderFactory:
    _providers: Dict[str, EmbeddingProvider] = {}
    _lock = threading.Lock()

    @staticmethod
    def resolve_model_name(model_name: str) -> str:
        if not model_name:
            return "BAAI/bge-small-en-v1.5"
        return _MODEL_NAME_ALIASES.get(model_name.lower(), model_name)

    @classmethod
    def get_provider(
        cls, provider_name: str, model_name: str, deterministic: bool = True
    ) -> EmbeddingProvider:
        resolved_model = cls.resolve_model_name(model_name)
        provider_key = f"{provider_name}:{resolved_model}:{deterministic}"
        with cls._lock:
            if provider_key in cls._providers:
                return cls._providers[provider_key]

            if provider_name == "sentence-transformers":
                provider = SentenceTransformerProvider(resolved_model, deterministic)
            else:
                raise ValueError(f"Unknown embedding provider: {provider_name}")

            cls._providers[provider_key] = provider
            return provider
