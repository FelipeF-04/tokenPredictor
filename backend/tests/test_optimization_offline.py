import unittest
from unittest import mock

from optimization.embeddings import EmbeddingProviderFactory
from optimization.pipeline import OptimizationPipeline
from tokenizer import set_encoding
from tests.fakes import FakeEmbeddingProvider, FakeEncoding


class OfflineOptimizationTests(unittest.TestCase):
    def setUp(self):
        set_encoding(FakeEncoding())

    def test_pipeline_uses_fake_embeddings_without_model_initialization(self):
        provider = FakeEmbeddingProvider()
        pipeline = OptimizationPipeline()
        payload = {
            "session_id": "offline-optimization",
            "model_profile": "local-8k",
            "messages": [
                {"role": "user", "content": "Keep this context for the answer."},
                {"role": "assistant", "content": "Context retained."},
                {"role": "user", "content": "Now summarize it concisely."},
            ],
            "options": {"include_trace": False},
        }

        with mock.patch.object(
            EmbeddingProviderFactory,
            "get_provider",
            return_value=provider,
        ) as get_provider:
            result = pipeline.optimize(payload)

        get_provider.assert_called_once()
        self.assertEqual(result["session_id"], "offline-optimization")
        self.assertEqual(result["model_profile"], "local-8k")
        self.assertIn("rendered_prompt", result["optimized"])
        self.assertNotIn("trace", result)
