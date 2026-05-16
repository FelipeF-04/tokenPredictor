import json
import math
import re
from pathlib import Path

DEFAULT_MULTIPLIER = 1.5
CODE_MULTIPLIER = 1.8
SHORT_MULTIPLIER = 1.2
SHORT_TOKEN_THRESHOLD = 50

_CODE_PATTERN = re.compile(
    r"\b(function|class|import|def|return|var|let|const|public|private|protected)\b|```",
    re.IGNORECASE,
)


def _load_config():
    config_path = Path(__file__).resolve().parents[1] / "shared" / "config.json"
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


_config = _load_config()

TOKEN_WINDOW = int(_config.get("token_window", 8000))
RISK_YELLOW = float(_config.get("risk_thresholds", {}).get("yellow", 0.6))
RISK_RED = float(_config.get("risk_thresholds", {}).get("red", 0.85))
OUTPUT_ESTIMATE_MIN_TOKENS = int(_config.get("output_estimate_min_tokens", 30))


def pick_multiplier(message, input_tokens):
    if input_tokens < SHORT_TOKEN_THRESHOLD:
        return SHORT_MULTIPLIER
    if message and _CODE_PATTERN.search(message):
        return CODE_MULTIPLIER
    return DEFAULT_MULTIPLIER


def predict_output_tokens(message, input_tokens):
    if input_tokens <= 0:
        return 0
    if OUTPUT_ESTIMATE_MIN_TOKENS > 0 and input_tokens < OUTPUT_ESTIMATE_MIN_TOKENS:
        return 0
    multiplier = pick_multiplier(message, input_tokens)
    return int(math.ceil(input_tokens * multiplier))


def risk_level(current_session_tokens, projected_total_tokens):
    if TOKEN_WINDOW <= 0:
        return "red"
    risk_score = (current_session_tokens + projected_total_tokens) / TOKEN_WINDOW
    if risk_score >= RISK_RED:
        return "red"
    if risk_score >= RISK_YELLOW:
        return "yellow"
    return "green"
