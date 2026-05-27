from contextlib import contextmanager
from dataclasses import dataclass, field
import time
from typing import Dict


@dataclass
class PipelineProfiler:
    started_at: float = field(default_factory=time.perf_counter)
    stages: Dict[str, float] = field(default_factory=dict)

    @contextmanager
    def track(self, name: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.stages[name] = self.stages.get(name, 0.0) + elapsed_ms

    def total_ms(self) -> float:
        return (time.perf_counter() - self.started_at) * 1000

    def to_dict(self) -> Dict[str, float]:
        payload = {"total_ms": self.total_ms()}
        for name, duration in self.stages.items():
            payload[f"{name}_ms"] = duration
        return payload
