"""
Unit Test: SQLite Database & Thread Writer Queue Validation
"""

import unittest
import time
from ares_app.database import init_database, start_db_service, db_read, db_enqueue


class TestDatabase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        start_db_service()

    def test_database_tables_exist(self):
        roles = db_read("SELECT * FROM roles")
        self.assertTrue(len(roles) >= 3)

        role_names = [r["name"] for r in roles]
        self.assertIn("admin", role_names)
        self.assertIn("operator", role_names)
        self.assertIn("auditor", role_names)

        users = db_read("SELECT * FROM users")
        self.assertTrue(len(users) >= 3)
        usernames = [u["username"] for u in users]
        self.assertIn("admin", usernames)

    def test_db_enqueue_and_read(self):
        test_session_id = "test_unit_sess_01"

        # Cleanup existing if any
        db_enqueue("DELETE FROM sessions WHERE session_id = ?", (test_session_id,))
        time.sleep(0.5)

        db_enqueue(
            "INSERT INTO sessions (session_id, start_time, mode, video_filename) VALUES (?, ?, ?, ?)",
            (test_session_id, "2026-08-11T00:00:00Z", "Autonomous", "unit_test_feed.mp4")
        )
        time.sleep(0.5)

        rows = db_read("SELECT * FROM sessions WHERE session_id = ?", (test_session_id,))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["session_id"], test_session_id)
        self.assertEqual(rows[0]["video_filename"], "unit_test_feed.mp4")

        # Cleanup
        db_enqueue("DELETE FROM sessions WHERE session_id = ?", (test_session_id,))
        time.sleep(0.5)


if __name__ == '__main__':
    unittest.main()
