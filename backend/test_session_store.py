import os
import tempfile
import unittest

from storage.session_store import SessionStore


class SessionStoreTests(unittest.TestCase):
    def test_create_commit_reset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "sessions.db")
            store = SessionStore(db_path, ttl_seconds=0)

            session = store.get_or_create("test-session", model_profile="gpt-4o-mini")
            self.assertEqual(session.total_tokens, 0)

            session = store.commit_tokens("test-session", 120, model_profile="gpt-4o-mini")
            self.assertEqual(session.total_tokens, 120)

            session = store.reset_session("test-session")
            self.assertEqual(session.total_tokens, 0)

            loaded = store.get("test-session")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.total_tokens, 0)

    def test_prune(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "sessions.db")
            store = SessionStore(db_path, ttl_seconds=1)
            store.get_or_create("stale")
            store._db.execute(
                "UPDATE sessions SET last_updated = ? WHERE session_id = ?",
                (0, "stale"),
            )
            store.prune()
            self.assertIsNone(store.get("stale"))


if __name__ == "__main__":
    unittest.main()
