from collections import OrderedDict
from dataclasses import dataclass
import threading
from typing import List, Optional


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    sets: int = 0
    evictions: int = 0

    def hit_rate(self) -> float:
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total


class EmbeddingCache:
    def __init__(self, max_size: int = 20000) -> None:
        self._max_size = max_size
        self._store: "OrderedDict[str, List[float]]" = OrderedDict()
        self._lock = threading.Lock()
        self.stats = CacheStats()

    def get(self, key: str) -> Optional[List[float]]:
        with self._lock:
            value = self._store.get(key)
            if value is not None:
                self._store.move_to_end(key)
                self.stats.hits += 1
            else:
                self.stats.misses += 1
            return value

    def set(self, key: str, value: List[float]) -> None:
        with self._lock:
            self._store[key] = value
            self._store.move_to_end(key)
            self.stats.sets += 1
            if len(self._store) > self._max_size:
                self._store.popitem(last=False)
                self.stats.evictions += 1


class EmbeddingStore:
    def __init__(self, cache: Optional[EmbeddingCache] = None) -> None:
        self._cache = cache or EmbeddingCache()

    def get(self, session_id: str, key: str) -> (Optional[List[float]], str):
        session_key = f"{session_id}:{key}"
        value = self._cache.get(session_key)
        if value is not None:
            return value, "session"
        value = self._cache.get(key)
        if value is not None:
            return value, "global"
        return None, "miss"

    def set(self, session_id: str, key: str, value: List[float]) -> None:
        session_key = f"{session_id}:{key}"
        self._cache.set(session_key, value)
        self._cache.set(key, value)

    def stats(self) -> CacheStats:
        return self._cache.stats
