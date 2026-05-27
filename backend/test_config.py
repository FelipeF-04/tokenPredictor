import unittest

from config.schema import ConfigError, build_config


class ConfigSchemaTests(unittest.TestCase):
    def test_build_config_defaults(self):
        config = build_config({})
        self.assertEqual(config.token_window, 8000)
        self.assertEqual(config.risk_thresholds.yellow, 0.6)
        self.assertEqual(config.risk_thresholds.red, 0.85)

    def test_invalid_threshold_order(self):
        with self.assertRaises(ConfigError):
            build_config({"risk_thresholds": {"yellow": 0.9, "red": 0.2}})

    def test_custom_backend_settings(self):
        config = build_config({"backend": {"session_ttl_seconds": 10}})
        self.assertEqual(config.backend.session_ttl_seconds, 10)


if __name__ == "__main__":
    unittest.main()
