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


@dataclass
class ConversationEventRecord:
    session_id: str
    event_id: str
    role: str
    token_count: int
    content_hash: str
    created_at: float
    updated_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "event_id": self.event_id,
            "role": self.role,
            "token_count": self.token_count,
            "content_hash": self.content_hash,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class LedgerWriteResult:
    status: str
    event: ConversationEventRecord
    session: SessionRecord
