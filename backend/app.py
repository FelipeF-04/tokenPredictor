from pathlib import Path

from flask import Flask, jsonify, request

from config import load_config
from predictor import predict_output_tokens, risk_level
from storage import SessionStore
from tokenizer import TokenizerUnavailableError, count_tokens
from optimization.pipeline import OptimizationPipeline

app = Flask(__name__)

MAX_ANALYZE_MESSAGE_CHARS = 100_000

_config = load_config()
_pipeline = OptimizationPipeline()
_storage_path = Path(_config.backend.storage_path)
if not _storage_path.is_absolute():
    _storage_path = Path(__file__).resolve().parents[1] / _storage_path

_session_store = SessionStore(
    str(_storage_path), ttl_seconds=_config.backend.session_ttl_seconds
)


def _json_error(message, status=400):
    response = jsonify({"error": message})
    return response, status


def _json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, _json_error("request body must be a JSON object")
    return data, None


@app.after_request
def _add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


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
        return _json_error(str(exc), status=503)

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
        return _json_error(str(exc), status=503)
    except Exception:
        return _json_error("optimization failed", status=500)

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
    app.run(host="0.0.0.0", port=5000, debug=True)
