from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class SessionRecord:
    session_id: str
    total_tokens: int
    created_at: float
    last_updated: float
    model_profile: Optional[str] = None
    optimization_stats: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "total_tokens": self.total_tokens,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "model_profile": self.model_profile,
            "optimization_stats": self.optimization_stats or {},
        }
