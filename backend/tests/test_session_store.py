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

    def test_event_idempotency_and_token_correction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(os.path.join(tmpdir, "ledger.db"), ttl_seconds=0)

            created = store.record_event(
                "ledger-session", "turn-1:user", "user", 4, "hash-user"
            )
            unchanged = store.record_event(
                "ledger-session", "turn-1:user", "user", 4, "hash-user"
            )
            assistant = store.record_event(
                "ledger-session", "turn-2:assistant", "assistant", 8, "hash-long"
            )
            updated = store.record_event(
                "ledger-session", "turn-2:assistant", "assistant", 3, "hash-short"
            )

            self.assertEqual(created.status, "created")
            self.assertEqual(created.session.total_tokens, 4)
            self.assertEqual(unchanged.status, "unchanged")
            self.assertEqual(unchanged.session.total_tokens, 4)
            self.assertEqual(assistant.session.total_tokens, 12)
            self.assertEqual(updated.status, "updated")
            self.assertEqual(updated.session.total_tokens, 7)
            self.assertEqual(len(store.list_events("ledger-session")), 2)

    def test_event_ledger_persists_and_reset_clears_it(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "persistent-ledger.db")
            first_store = SessionStore(db_path, ttl_seconds=0)
            first_store.record_event(
                "persistent", "turn-1:user", "user", 5, "persistent-hash"
            )

            reopened_store = SessionStore(db_path, ttl_seconds=0)
            event = reopened_store.get_event("persistent", "turn-1:user")
            session = reopened_store.get("persistent")
            self.assertIsNotNone(event)
            self.assertEqual(event.token_count, 5)
            self.assertEqual(session.total_tokens, 5)

            reset = reopened_store.reset_session("persistent")
            self.assertEqual(reset.total_tokens, 0)
            self.assertEqual(reopened_store.list_events("persistent"), [])

    def test_event_role_cannot_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(os.path.join(tmpdir, "roles.db"), ttl_seconds=0)
            store.record_event("roles", "turn-1", "user", 2, "hash")

            with self.assertRaisesRegex(ValueError, "role cannot change"):
                store.record_event("roles", "turn-1", "assistant", 3, "new-hash")

            self.assertEqual(store.get("roles").total_tokens, 2)


if __name__ == "__main__":
    unittest.main()
