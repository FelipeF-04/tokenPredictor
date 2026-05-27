import json
from pathlib import Path
from typing import Optional

from .schema import AppConfig, ConfigError, build_config


_CONFIG_CACHE: Optional[AppConfig] = None


def _config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "shared" / "config.json"


def load_config(force_reload: bool = False) -> AppConfig:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None and not force_reload:
        return _CONFIG_CACHE

    config_path = _config_path()
    raw = {}
    if config_path.exists():
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}

    try:
        config = build_config(raw)
    except ConfigError:
        config = AppConfig()

    _CONFIG_CACHE = config
    return config
