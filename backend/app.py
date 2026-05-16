from flask import Flask, jsonify, request

from predictor import predict_output_tokens, risk_level
from tokenizer import count_tokens
from optimization.pipeline import OptimizationPipeline

app = Flask(__name__)

_session_tokens = 0
_pipeline = OptimizationPipeline()


def _json_error(message, status=400):
    response = jsonify({"error": message})
    return response, status


@app.after_request
def _add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response


def _handle_options():
    return ("", 204)


@app.route("/analyze", methods=["POST", "OPTIONS"])
def analyze():
    if request.method == "OPTIONS":
        return _handle_options()

    data = request.get_json(silent=True) or {}
    message = data.get("message", "")
    if not isinstance(message, str):
        return _json_error("message must be a string")

    input_tokens = count_tokens(message)
    predicted_output_tokens = predict_output_tokens(message, input_tokens)
    projected_total_tokens = input_tokens + predicted_output_tokens
    risk = risk_level(_session_tokens, projected_total_tokens)

    return jsonify(
        {
            "input_tokens": input_tokens,
            "predicted_output_tokens": predicted_output_tokens,
            "projected_total_tokens": projected_total_tokens,
            "risk_level": risk,
        }
    )


@app.route("/commit", methods=["POST", "OPTIONS"])
def commit():
    if request.method == "OPTIONS":
        return _handle_options()

    data = request.get_json(silent=True) or {}
    reset = bool(data.get("reset", False))

    global _session_tokens
    if reset:
        _session_tokens = 0
        return jsonify({"session_tokens": _session_tokens})

    delta_tokens = data.get("delta_tokens")
    if delta_tokens is None:
        return _json_error("delta_tokens is required unless reset is true")

    try:
        delta_value = int(delta_tokens)
    except (TypeError, ValueError):
        return _json_error("delta_tokens must be an integer")

    if delta_value <= 0:
        return _json_error("delta_tokens must be > 0")

    _session_tokens += delta_value
    return jsonify({"session_tokens": _session_tokens})


@app.route("/optimize", methods=["POST", "OPTIONS"])
def optimize():
    if request.method == "OPTIONS":
        return _handle_options()

    data = request.get_json(silent=True) or {}
    try:
        result = _pipeline.optimize(data)
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception:
        return _json_error("optimization failed", status=500)

    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
