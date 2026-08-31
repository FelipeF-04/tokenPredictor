import importlib
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

import tokenizer
from tests.fakes import FakeEncoding


class TokenizerTests(unittest.TestCase):
    def tearDown(self):
        tokenizer.set_encoding(FakeEncoding())

    def test_module_import_does_not_initialize_encoding(self):
        tokenizer_path = Path(__file__).resolve().parents[1] / "tokenizer.py"
        spec = importlib.util.spec_from_file_location("tokenizer_import_probe", tokenizer_path)
        module = importlib.util.module_from_spec(spec)

        with mock.patch("tiktoken.get_encoding") as get_encoding:
            spec.loader.exec_module(module)

        get_encoding.assert_not_called()

    def test_loader_is_lazy_and_cached(self):
        loader = mock.Mock(return_value=FakeEncoding())
        tokenizer.reset_encoding_cache(loader=loader)

        self.assertEqual(loader.call_count, 0)
        self.assertEqual(tokenizer.count_tokens("one two three"), 3)
        self.assertEqual(tokenizer.count_tokens("four five"), 2)
        loader.assert_called_once_with("cl100k_base")

    def test_importing_application_does_not_load_encoding(self):
        loader = mock.Mock(return_value=FakeEncoding())
        tokenizer.reset_encoding_cache(loader=loader)

        import app as backend_app

        importlib.reload(backend_app)
        loader.assert_not_called()

    def test_unavailable_encoding_raises_intentional_error(self):
        def unavailable(_name):
            raise OSError("offline")

        tokenizer.reset_encoding_cache(loader=unavailable)

        with self.assertRaisesRegex(
            tokenizer.TokenizerUnavailableError,
            "Tokenizer encoding 'cl100k_base' is unavailable",
        ):
            tokenizer.count_tokens("requires encoding")


if __name__ == "__main__":
    unittest.main()
