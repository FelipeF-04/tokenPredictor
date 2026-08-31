import unittest

from optimization.incremental.chunking import IncrementalChunker
from optimization.models import Message, SessionState
from optimization.semantic_chunker import SemanticChunker
from tokenizer import set_encoding
from tests.fakes import FakeEncoding


class IncrementalChunkingTests(unittest.TestCase):
    def setUp(self):
        set_encoding(FakeEncoding())

    def test_reuse_stats(self):
        session = SessionState(session_id="s1")
        chunker = IncrementalChunker(SemanticChunker(max_tokens=200, overlap_tokens=0))
        messages = [Message(role="user", content="Hello world", message_id="m1")]

        chunks, stats = chunker.build_chunks(session, messages)
        self.assertEqual(stats.messages_reused, 0)
        self.assertEqual(stats.messages_total, 1)
        self.assertGreater(len(chunks), 0)

        chunks2, stats2 = chunker.build_chunks(session, messages)
        self.assertEqual(stats2.messages_reused, 1)
        self.assertEqual(stats2.messages_total, 1)
        self.assertEqual(stats2.chunk_reuse_rate(), 1.0)
        self.assertEqual(len(chunks2), len(chunks))


if __name__ == "__main__":
    unittest.main()
