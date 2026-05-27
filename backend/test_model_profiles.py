import unittest

from optimization.models import default_model_profiles


class ModelProfileTests(unittest.TestCase):
    def test_default_profiles_present(self):
        profiles = default_model_profiles()
        required = {"gpt-4o-mini", "gpt-4.1", "gpt-5", "local-8k", "local-16k"}
        self.assertTrue(required.issubset(set(profiles.keys())))
        for name in required:
            self.assertGreater(profiles[name].context_window, 0)


if __name__ == "__main__":
    unittest.main()
