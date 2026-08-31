import unittest

from optimization.cache.embedding_cache import EmbeddingStore


class EmbeddingStoreTests(unittest.TestCase):
    def test_session_and_global_hits(self):
        store = EmbeddingStore()
        session_id = "session-1"
        key = "key-1"
        vector = [0.1, 0.2]

        value, source = store.get(session_id, key)
        self.assertIsNone(value)
        self.assertEqual(source, "miss")

        store.set(session_id, key, vector)

        value, source = store.get(session_id, key)
        self.assertEqual(value, vector)
        self.assertEqual(source, "session")

        value, source = store.get("other", key)
        self.assertEqual(value, vector)
        self.assertEqual(source, "global")


if __name__ == "__main__":
    unittest.main()
