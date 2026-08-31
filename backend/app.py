import hashlib
import json
import os
from pathlib import Path
import re

from flask import Flask, jsonify, request

from config import load_config
from predictor import predict_output_tokens, risk_level
from storage import SessionStore
from tokenizer import TokenizerUnavailableError, count_tokens
from optimization.pipeline import OptimizationPipeline

app = Flask(__name__)

MAX_ANALYZE_MESSAGE_CHARS = 100_000
MAX_REQUEST_BYTES = 1_048_576
MAX_EVENT_ID_CHARS = 256
MAX_SESSION_ID_CHARS = 128
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000
_CHROME_EXTENSION_ORIGIN = re.compile(r"^chrome-extension://[a-p]{32}$")
_LOOPBACK_ORIGIN = re.compile(r"^https?://(?:localhost|127\.0\.0\.1)(?::\d+)?$")

app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES

_config = load_config()
_pipeline = OptimizationPipeline()
_storage_path = Path(
    os.environ.get("AI_USAGE_STORAGE_PATH") or _config.backend.storage_path
)
if not _storage_path.is_absolute():
    _storage_path = Path(__file__).resolve().parents[1] / _storage_path

_session_store = SessionStore(
    str(_storage_path), ttl_seconds=_config.backend.session_ttl_seconds
)


def _runtime_mode(environ=None):
    source = environ if environ is not None else os.environ
    return source.get("AI_USAGE_ENV", "production").strip().lower()


def _is_truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _server_options(environ=None):
    source = environ if environ is not None else os.environ
    host = source.get("AI_USAGE_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST
    try:
        port = int(source.get("AI_USAGE_PORT", DEFAULT_PORT))
    except (TypeError, ValueError):
        port = DEFAULT_PORT
    if not 1 <= port <= 65_535:
        port = DEFAULT_PORT
    debug = _runtime_mode(source) == "development" and _is_truthy(
        source.get("AI_USAGE_DEBUG")
    )
    return {"host": host, "port": port, "debug": debug}


def _configured_origins(environ=None):
    source = environ if environ is not None else os.environ
    raw = source.get("AI_USAGE_ALLOWED_ORIGINS", "")
    return {origin.strip() for origin in raw.split(",") if origin.strip()}


def _is_allowed_origin(origin, environ=None):
    if not origin:
        return False
    if origin in _configured_origins(environ):
        return True
    if _runtime_mode(environ) != "development":
        return False
    return bool(
        _CHROME_EXTENSION_ORIGIN.fullmatch(origin)
        or _LOOPBACK_ORIGIN.fullmatch(origin)
    )


def _log_request_error(status, error_type, exception=None):
    details = {
        "event": "request_error",
        "error_type": error_type,
        "method": request.method,
        "path": request.path,
        "status": status,
    }
    if exception is not None:
        details["exception_type"] = type(exception).__name__
    app.logger.warning(json.dumps(details, sort_keys=True, separators=(",", ":")))


def _json_error(message, status=400, log_event=None, exception=None):
    if log_event:
        _log_request_error(status, log_event, exception)
    response = jsonify({"error": message})
    return response, status


def _json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, _json_error("request body must be a JSON object")
    return data, None


@app.after_request
def _add_cors_headers(response):
    origin = request.headers.get("Origin")
    if _is_allowed_origin(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers.add("Vary", "Origin")
    return response


@app.errorhandler(413)
def _request_too_large(_error):
    return _json_error(
        f"request body must be at most {MAX_REQUEST_BYTES} bytes",
        status=413,
        log_event="request_too_large",
    )


def _handle_options():
    return ("", 204)


def _resolve_model_profile(name):
    profile_name = name or _config.default_model_profile
    profile = _pipeline.model_profiles.get(profile_name)
    if profile is None:
        raise ValueError(f"Unknown model_profile: {profile_name}")
    return profile


@app.route("/analyze", methods=["POST", "OPTIONS"])
def analyze():
    if request.method == "OPTIONS":
        return _handle_options()

    data, error = _json_object()
    if error:
        return error

    message = data.get("message", "")
    if not isinstance(message, str):
        return _json_error("message must be a string")
    if len(message) > MAX_ANALYZE_MESSAGE_CHARS:
        return _json_error(
            f"message must be at most {MAX_ANALYZE_MESSAGE_CHARS} characters",
            status=413,
            log_event="message_too_large",
        )

    session_id = data.get("session_id")
    model_profile = data.get("model_profile")
    try:
        profile = _resolve_model_profile(model_profile)
    except ValueError as exc:
        return _json_error(str(exc))

    session = _session_store.get_or_create(session_id, model_profile)

    try:
        input_tokens = count_tokens(message)
    except TokenizerUnavailableError as exc:
        return _json_error(
            str(exc), status=503, log_event="tokenizer_unavailable", exception=exc
        )

    predicted_output_tokens = predict_output_tokens(message, input_tokens)
    projected_total_tokens = input_tokens + predicted_output_tokens
    context_window = profile.context_window or _config.token_window
    reserved_output_tokens = min(max(profile.max_output_tokens, 0), context_window)
    projected_session_tokens = session.total_tokens + projected_total_tokens
    available_context_tokens = max(
        context_window - reserved_output_tokens - session.total_tokens - input_tokens,
        0,
    )
    utilization_ratio = (
        projected_session_tokens / context_window if context_window > 0 else 1.0
    )
    risk = risk_level(
        session.total_tokens,
        projected_total_tokens,
        token_window=context_window,
    )

    return jsonify(
        {
            "input_tokens": input_tokens,
            "predicted_output_tokens": predicted_output_tokens,
            "projected_total_tokens": projected_total_tokens,
            "risk_level": risk,
            "session_id": session.session_id,
            "session_tokens": session.total_tokens,
            "context_window": context_window,
            "reserved_output_tokens": reserved_output_tokens,
            "available_context_tokens": available_context_tokens,
            "utilization_ratio": utilization_ratio,
        }
    )


@app.route("/commit", methods=["POST", "OPTIONS"])
def commit():
    if request.method == "OPTIONS":
        return _handle_options()

    data = request.get_json(silent=True) or {}
    reset = bool(data.get("reset", False))
    session_id = data.get("session_id")
    model_profile = data.get("model_profile")
    if reset:
        if not session_id:
            session_id = "default"
        session = _session_store.reset_session(session_id, model_profile)
        return jsonify({"session_id": session.session_id, "session_tokens": session.total_tokens})

    delta_tokens = data.get("delta_tokens")
    if delta_tokens is None:
        return _json_error("delta_tokens is required unless reset is true")

    try:
        delta_value = int(delta_tokens)
    except (TypeError, ValueError):
        return _json_error("delta_tokens must be an integer")

    if delta_value <= 0:
        return _json_error("delta_tokens must be > 0")

    session = _session_store.commit_tokens(session_id, delta_value, model_profile)
    return jsonify({"session_id": session.session_id, "session_tokens": session.total_tokens})


@app.route("/events", methods=["POST", "OPTIONS"])
def record_conversation_event():
    if request.method == "OPTIONS":
        return _handle_options()

    data, error = _json_object()
    if error:
        return error

    session_id = data.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        return _json_error("session_id must be a non-empty string")
    session_id = session_id.strip()
    if len(session_id) > MAX_SESSION_ID_CHARS:
        return _json_error(
            f"session_id must be at most {MAX_SESSION_ID_CHARS} characters"
        )

    event_id = data.get("event_id")
    if not isinstance(event_id, str) or not event_id.strip():
        return _json_error("event_id must be a non-empty string")
    event_id = event_id.strip()
    if len(event_id) > MAX_EVENT_ID_CHARS:
        return _json_error(
            f"event_id must be at most {MAX_EVENT_ID_CHARS} characters"
        )

    role = data.get("role")
    if role not in {"user", "assistant"}:
        return _json_error("role must be user or assistant")

    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        return _json_error("text must be a non-empty string")
    text = text.strip()
    if len(text) > MAX_ANALYZE_MESSAGE_CHARS:
        return _json_error(
            f"text must be at most {MAX_ANALYZE_MESSAGE_CHARS} characters",
            status=413,
            log_event="event_text_too_large",
        )

    model_profile = data.get("model_profile")
    try:
        profile = _resolve_model_profile(model_profile)
    except ValueError as exc:
        return _json_error(str(exc))

    try:
        token_count = count_tokens(text)
    except TokenizerUnavailableError as exc:
        return _json_error(
            str(exc), status=503, log_event="tokenizer_unavailable", exception=exc
        )

    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    try:
        result = _session_store.record_event(
            session_id=session_id,
            event_id=event_id,
            role=role,
            token_count=token_count,
            content_hash=content_hash,
            model_profile=profile.name,
        )
    except ValueError as exc:
        return _json_error(str(exc))

    context_window = profile.context_window or _config.token_window
    reserved_output_tokens = min(max(profile.max_output_tokens, 0), context_window)
    corrected_total = result.session.total_tokens
    available_context_tokens = max(
        context_window - reserved_output_tokens - corrected_total,
        0,
    )
    utilization_ratio = corrected_total / context_window if context_window > 0 else 1.0
    risk = risk_level(corrected_total, 0, token_window=context_window)

    return jsonify(
        {
            "event_status": result.status,
            "event_id": result.event.event_id,
            "event_role": result.event.role,
            "event_tokens": result.event.token_count,
            "content_hash": result.event.content_hash,
            "event_created_at": result.event.created_at,
            "event_updated_at": result.event.updated_at,
            "session_id": result.session.session_id,
            "session_tokens": corrected_total,
            "corrected_session_total": corrected_total,
            "context_window": context_window,
            "reserved_output_tokens": reserved_output_tokens,
            "available_context_tokens": available_context_tokens,
            "utilization_ratio": utilization_ratio,
            "risk_level": risk,
        }
    )


@app.route("/optimize", methods=["POST", "OPTIONS"])
def optimize():
    if request.method == "OPTIONS":
        return _handle_options()

    data = request.get_json(silent=True) or {}
    try:
        result = _pipeline.optimize(data)
        session_id = result.get("session_id")
        model_profile = result.get("model_profile")
        if session_id:
            _session_store.get_or_create(session_id, model_profile)
            _session_store.update_optimization_stats(
                session_id,
                {
                    "model_profile": model_profile,
                    "metrics": result.get("metrics", {}),
                    "stats": result.get("stats", {}),
                    "profiling": result.get("profiling", {}),
                },
            )
    except ValueError as exc:
        return _json_error(str(exc))
    except TokenizerUnavailableError as exc:
        return _json_error(
            str(exc), status=503, log_event="tokenizer_unavailable", exception=exc
        )
    except Exception as exc:
        return _json_error(
            "optimization failed",
            status=500,
            log_event="optimization_failed",
            exception=exc,
        )

    return jsonify(result)


@app.route("/config", methods=["GET", "OPTIONS"])
def config():
    if request.method == "OPTIONS":
        return _handle_options()
    return jsonify(_config.to_public_dict())


@app.route("/models", methods=["GET", "OPTIONS"])
def models():
    if request.method == "OPTIONS":
        return _handle_options()
    profiles = [
        {
            "name": profile.name,
            "context_window": profile.context_window,
            "max_output_tokens": profile.max_output_tokens,
            "system_ratio": profile.system_ratio,
            "instruction_ratio": profile.instruction_ratio,
            "memory_ratio": profile.memory_ratio,
            "retrieval_ratio": profile.retrieval_ratio,
            "compression_tolerance": profile.compression_tolerance,
            "tokenizer": profile.tokenizer,
        }
        for profile in _pipeline.model_profiles.values()
    ]
    return jsonify({"models": profiles})


@app.route("/session/<session_id>", methods=["GET", "OPTIONS"])
def get_session(session_id):
    if request.method == "OPTIONS":
        return _handle_options()
    session = _session_store.get(session_id)
    if session is None:
        return _json_error("session not found", status=404)
    return jsonify(session.to_dict())


@app.route("/session/<session_id>/reset", methods=["POST", "OPTIONS"])
def reset_session(session_id):
    if request.method == "OPTIONS":
        return _handle_options()
    data = request.get_json(silent=True) or {}
    model_profile = data.get("model_profile")
    session = _session_store.reset_session(session_id, model_profile)
    return jsonify({"session_id": session.session_id, "session_tokens": session.total_tokens})


@app.route("/reset", methods=["POST", "OPTIONS"])
def reset_default_session():
    if request.method == "OPTIONS":
        return _handle_options()
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id") or "default"
    model_profile = data.get("model_profile")
    session = _session_store.reset_session(session_id, model_profile)
    return jsonify({"session_id": session.session_id, "session_tokens": session.total_tokens})


if __name__ == "__main__":
    app.run(**_server_options())
