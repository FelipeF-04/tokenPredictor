import math
import re

from config import load_config

DEFAULT_MULTIPLIER = 1.5
CODE_MULTIPLIER = 1.8
SHORT_MULTIPLIER = 1.2
SHORT_TOKEN_THRESHOLD = 50

_CODE_PATTERN = re.compile(
    r"\b(function|class|import|def|return|var|let|const|public|private|protected)\b|```",
    re.IGNORECASE,
)


_config = load_config()


def pick_multiplier(message, input_tokens):
    if input_tokens < SHORT_TOKEN_THRESHOLD:
        return SHORT_MULTIPLIER
    if message and _CODE_PATTERN.search(message):
        return CODE_MULTIPLIER
    return DEFAULT_MULTIPLIER


def predict_output_tokens(message, input_tokens):
    if input_tokens <= 0:
        return 0
    min_tokens = _config.output_estimate_min_tokens
    if min_tokens > 0 and input_tokens < min_tokens:
        return 0
    multiplier = pick_multiplier(message, input_tokens)
    return int(math.ceil(input_tokens * multiplier))


def risk_level(current_session_tokens, projected_total_tokens, token_window=None, thresholds=None):
    config = _config
    if token_window is None:
        token_window = config.token_window
    if thresholds is None:
        thresholds = config.risk_thresholds
    if token_window <= 0:
        return "red"
    risk_score = (current_session_tokens + projected_total_tokens) / token_window
    if risk_score >= thresholds.red:
        return "red"
    if risk_score >= thresholds.yellow:
        return "yellow"
    return "green"
