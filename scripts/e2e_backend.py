"""Start the Flask API with deterministic, offline-only E2E dependencies."""

import argparse
import os
from pathlib import Path
import signal
import sys
import threading


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"


class FakeEncoding:
    def encode(self, text):
        return str(text).split()


class FakeEmbeddingProvider:
    name = "fake"
    model_name = "fake-e2e-embedding"
    deterministic = True

    def embed_texts(self, texts):
        vectors = []
        for text in texts:
            checksum = sum(ord(character) for character in text)
            vectors.append(
                [
                    (checksum % 997) / 997,
                    (len(text) % 127) / 127,
                    1.0,
                ]
            )
        return vectors


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, help="temporary SQLite path")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=5000, type=int)
    return parser.parse_args()


def main():
    arguments = parse_args()
    database_path = Path(arguments.database).resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    os.environ.update(
        {
            "AI_USAGE_ENV": "development",
            "AI_USAGE_DEBUG": "0",
            "AI_USAGE_HOST": arguments.host,
            "AI_USAGE_PORT": str(arguments.port),
            "AI_USAGE_STORAGE_PATH": str(database_path),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    sys.path.insert(0, str(BACKEND_ROOT))

    import app as app_module
    import tokenizer
    from optimization.embeddings import EmbeddingProviderFactory
    from werkzeug.serving import make_server

    tokenizer.set_encoding(FakeEncoding())
    fake_provider = FakeEmbeddingProvider()

    def get_fake_provider(_cls, _provider_name, _model_name, _deterministic=True):
        return fake_provider

    EmbeddingProviderFactory.get_provider = classmethod(get_fake_provider)

    availability = {"online": True}

    @app_module.app.before_request
    def simulate_backend_availability():
        from flask import jsonify, request

        if request.path.startswith("/__e2e__/"):
            return None
        if not availability["online"]:
            return jsonify({"error": "E2E backend intentionally unavailable"}), 503
        return None

    @app_module.app.get("/__e2e__/health")
    def e2e_health():
        from flask import jsonify

        return jsonify({"ready": True, "database": database_path.name})

    @app_module.app.post("/__e2e__/availability")
    def e2e_availability():
        from flask import jsonify, request

        payload = request.get_json(silent=True) or {}
        availability["online"] = bool(payload.get("online", True))
        return jsonify({"online": availability["online"]})

    server = make_server(arguments.host, arguments.port, app_module.app, threaded=True)

    def request_shutdown(_signum, _frame):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)
    print(
        f"E2E backend ready at http://{arguments.host}:{arguments.port} "
        f"using {database_path}",
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
