import tempfile
import unittest

import app as app_module
from storage.session_store import SessionStore
from tokenizer import set_encoding


class FakeEncoding:
    def encode(self, text):
        return text.split()


class AnalyzeEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        app_module._session_store = SessionStore(
            f"{self.temp_dir.name}/sessions.db", ttl_seconds=0
        )
        set_encoding(FakeEncoding())
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_analyze_returns_model_context_fields(self):
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
        response = self.client.post(
            "/analyze",
            json={"message": "x" * (app_module.MAX_ANALYZE_MESSAGE_CHARS + 1)},
        )

        self.assertEqual(response.status_code, 413)
        self.assertIn("at most", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
