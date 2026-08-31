import tempfile
import unittest

import app as app_module
from storage.session_store import SessionStore
import tokenizer
from tests.fakes import FakeEncoding


class AnalyzeEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        app_module._session_store = SessionStore(
            f"{self.temp_dir.name}/sessions.db", ttl_seconds=0
        )
        tokenizer.set_encoding(FakeEncoding())
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_analyze_success_contract_fields_and_types(self):
        response = self.client.post(
            "/analyze",
            json={
                "message": "one two three",
                "session_id": "analyze-session",
                "model_profile": "gpt-4o-mini",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        expected_fields = {
            "input_tokens",
            "predicted_output_tokens",
            "projected_total_tokens",
            "risk_level",
            "session_id",
            "session_tokens",
            "context_window",
            "reserved_output_tokens",
            "available_context_tokens",
            "utilization_ratio",
        }
        self.assertTrue(expected_fields.issubset(data))
        for field in {
            "input_tokens",
            "predicted_output_tokens",
            "projected_total_tokens",
            "session_tokens",
            "context_window",
            "reserved_output_tokens",
            "available_context_tokens",
        }:
            self.assertIs(type(data[field]), int, field)
        self.assertIs(type(data["utilization_ratio"]), float)
        self.assertIs(type(data["risk_level"]), str)
        self.assertIs(type(data["session_id"]), str)

        self.assertEqual(data["input_tokens"], 3)
        self.assertEqual(data["predicted_output_tokens"], 0)
        self.assertEqual(data["projected_total_tokens"], 3)
        self.assertEqual(data["context_window"], 128_000)
        self.assertEqual(data["reserved_output_tokens"], 2_048)
        self.assertEqual(data["available_context_tokens"], 125_949)
        self.assertAlmostEqual(data["utilization_ratio"], 3 / 128_000)
        self.assertEqual(data["risk_level"], "green")
        self.assertEqual(data["session_tokens"], 0)
        self.assertEqual(data["session_id"], "analyze-session")

    def test_analyze_rejects_non_object_or_malformed_json(self):
        responses = [
            self.client.post("/analyze", data="not-json", content_type="application/json"),
            self.client.post("/analyze", json=["not", "an", "object"]),
            self.client.post("/analyze", data="plain text", content_type="text/plain"),
        ]

        for response in responses:
            self.assertEqual(response.status_code, 400)
            self.assertIn("JSON object", response.get_json()["error"])

    def test_analyze_rejects_non_string_message(self):
        response = self.client.post("/analyze", json={"message": 42})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "message must be a string")

    def test_analyze_rejects_oversized_message(self):
        with self.assertLogs(app_module.app.logger, level="WARNING"):
            response = self.client.post(
                "/analyze",
                json={"message": "x" * (app_module.MAX_ANALYZE_MESSAGE_CHARS + 1)},
            )

        self.assertEqual(response.status_code, 413)
        self.assertIn("at most", response.get_json()["error"])

    def test_request_body_limit_rejects_large_json(self):
        with self.assertLogs(app_module.app.logger, level="WARNING"):
            response = self.client.post(
                "/analyze",
                json={"message": "x" * (app_module.MAX_REQUEST_BYTES + 1)},
            )

        self.assertEqual(response.status_code, 413)
        self.assertIn("request body", response.get_json()["error"])

    def test_unavailable_tokenizer_returns_structured_service_error(self):
        def unavailable(_name):
            raise OSError("offline detail must not be logged")

        tokenizer.reset_encoding_cache(loader=unavailable)
        with self.assertLogs(app_module.app.logger, level="WARNING") as captured:
            response = self.client.post(
                "/analyze",
                json={"message": "sensitive prompt text", "session_id": "offline"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("Tokenizer encoding", response.get_json()["error"])
        logs = "\n".join(captured.output)
        self.assertIn('"error_type":"tokenizer_unavailable"', logs)
        self.assertIn('"exception_type":"TokenizerUnavailableError"', logs)
        self.assertNotIn("sensitive prompt text", logs)
        self.assertNotIn("offline detail", logs)

    def test_analyze_uses_selected_model_profile(self):
        response = self.client.post(
            "/analyze",
            json={"message": "two tokens", "model_profile": "local-8k"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["context_window"], 8_192)
        self.assertEqual(data["reserved_output_tokens"], 1_024)
        self.assertEqual(data["available_context_tokens"], 7_166)

    def test_analyze_rejects_unknown_model_profile(self):
        response = self.client.post(
            "/analyze",
            json={"message": "hello", "model_profile": "not-a-model"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unknown model_profile", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
