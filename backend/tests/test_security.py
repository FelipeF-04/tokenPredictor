import os
import unittest
from unittest import mock

import app as app_module


class ProductionSafetyTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()

    def test_production_server_defaults_are_loopback_and_debug_off(self):
        options = app_module._server_options({})

        self.assertEqual(options["host"], "127.0.0.1")
        self.assertEqual(options["port"], 5000)
        self.assertFalse(options["debug"])

    def test_debug_requires_development_mode_and_explicit_flag(self):
        self.assertFalse(
            app_module._server_options(
                {"AI_USAGE_ENV": "production", "AI_USAGE_DEBUG": "1"}
            )["debug"]
        )
        self.assertTrue(
            app_module._server_options(
                {"AI_USAGE_ENV": "development", "AI_USAGE_DEBUG": "1"}
            )["debug"]
        )

    def test_production_cors_requires_an_exact_configured_origin(self):
        origin = "chrome-extension://" + ("a" * 32)
        with mock.patch.dict(os.environ, {}, clear=True):
            denied = self.client.get("/config", headers={"Origin": origin})
        self.assertNotIn("Access-Control-Allow-Origin", denied.headers)

        with mock.patch.dict(
            os.environ,
            {"AI_USAGE_ALLOWED_ORIGINS": origin},
            clear=True,
        ):
            allowed = self.client.get("/config", headers={"Origin": origin})
        self.assertEqual(allowed.headers["Access-Control-Allow-Origin"], origin)
        self.assertIn("Origin", allowed.headers["Vary"])

    def test_development_cors_accepts_loopback_and_extension_origins(self):
        extension_origin = "chrome-extension://" + ("b" * 32)
        environment = {"AI_USAGE_ENV": "development"}

        with mock.patch.dict(os.environ, environment, clear=True):
            for origin in (extension_origin, "http://localhost:3000"):
                with self.subTest(origin=origin):
                    response = self.client.get("/config", headers={"Origin": origin})
                    self.assertEqual(
                        response.headers["Access-Control-Allow-Origin"], origin
                    )

            denied = self.client.get(
                "/config", headers={"Origin": "https://untrusted.example"}
            )
            self.assertNotIn("Access-Control-Allow-Origin", denied.headers)


if __name__ == "__main__":
    unittest.main()
