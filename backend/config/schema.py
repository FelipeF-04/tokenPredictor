from dataclasses import dataclass, field
from typing import Any, Dict


class ConfigError(ValueError):
    pass


@dataclass
class RiskThresholds:
    yellow: float = 0.6
    red: float = 0.85


@dataclass
class DebugConfig:
    dom: bool = False
    pipeline: bool = False


@dataclass
class BackendConfig:
    session_ttl_seconds: int = 7200
    storage_path: str = "backend/storage/ai_usage.db"


@dataclass
class AppConfig:
    version: str = "1.1.0"
    backend_base_url: str = "http://localhost:5000"
    default_model_profile: str = "gpt-4o-mini"
    token_window: int = 8000
    output_estimate_min_tokens: int = 30
    risk_thresholds: RiskThresholds = field(default_factory=RiskThresholds)
    debug: DebugConfig = field(default_factory=DebugConfig)
    backend: BackendConfig = field(default_factory=BackendConfig)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "backend_base_url": self.backend_base_url,
            "default_model_profile": self.default_model_profile,
            "token_window": self.token_window,
            "output_estimate_min_tokens": self.output_estimate_min_tokens,
            "risk_thresholds": {
                "yellow": self.risk_thresholds.yellow,
                "red": self.risk_thresholds.red,
            },
            "debug": {
                "dom": self.debug.dom,
                "pipeline": self.debug.pipeline,
            },
            "backend": {
                "session_ttl_seconds": self.backend.session_ttl_seconds,
                "storage_path": self.backend.storage_path,
            },
        }

    def to_public_dict(self) -> Dict[str, Any]:
        data = self.to_dict()
        # Remove backend-only values not needed by the extension.
        data["backend"] = {"session_ttl_seconds": self.backend.session_ttl_seconds}
        return data


def _as_str(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _as_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed


def _as_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def build_config(raw: Dict[str, Any]) -> AppConfig:
    if not isinstance(raw, dict):
        raw = {}

    risk_raw = raw.get("risk_thresholds") if isinstance(raw.get("risk_thresholds"), dict) else {}
    yellow = _as_float(risk_raw.get("yellow"), RiskThresholds.yellow)
    red = _as_float(risk_raw.get("red"), RiskThresholds.red)

    if not 0 <= yellow <= 1:
        raise ConfigError("risk_thresholds.yellow must be between 0 and 1")
    if not 0 <= red <= 1:
        raise ConfigError("risk_thresholds.red must be between 0 and 1")
    if red < yellow:
        raise ConfigError("risk_thresholds.red must be >= risk_thresholds.yellow")

    debug_raw = raw.get("debug") if isinstance(raw.get("debug"), dict) else {}
    backend_raw = raw.get("backend") if isinstance(raw.get("backend"), dict) else {}

    token_window = _as_int(raw.get("token_window"), AppConfig.token_window)
    if token_window < 0:
        raise ConfigError("token_window must be >= 0")

    output_min = _as_int(raw.get("output_estimate_min_tokens"), AppConfig.output_estimate_min_tokens)
    if output_min < 0:
        raise ConfigError("output_estimate_min_tokens must be >= 0")

    session_ttl = _as_int(backend_raw.get("session_ttl_seconds"), BackendConfig.session_ttl_seconds)
    if session_ttl < 0:
        raise ConfigError("backend.session_ttl_seconds must be >= 0")

    return AppConfig(
        version=_as_str(raw.get("version"), AppConfig.version),
        backend_base_url=_as_str(raw.get("backend_base_url"), AppConfig.backend_base_url),
        default_model_profile=_as_str(
            raw.get("default_model_profile"), AppConfig.default_model_profile
        ),
        token_window=token_window,
        output_estimate_min_tokens=output_min,
        risk_thresholds=RiskThresholds(yellow=yellow, red=red),
        debug=DebugConfig(
            dom=_as_bool(debug_raw.get("dom"), DebugConfig.dom),
            pipeline=_as_bool(debug_raw.get("pipeline"), DebugConfig.pipeline),
        ),
        backend=BackendConfig(
            session_ttl_seconds=session_ttl,
            storage_path=_as_str(backend_raw.get("storage_path"), BackendConfig.storage_path),
        ),
    )
