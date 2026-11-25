import sqlite3
import types
import unittest
from unittest.mock import Mock

from pipeline import ig_once


class InstagramIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute(
            "CREATE TABLE igq (id INTEGER PRIMARY KEY, story_id INT, channel TEXT, "
            "path TEXT, caption TEXT, publish_at TEXT, status TEXT DEFAULT 'pending')"
        )
        self.connection.execute(
            "INSERT INTO igq (story_id, channel, path, caption, publish_at) "
            "VALUES (1, 'te', 'one.mp4', 'caption', '2026-01-01')"
        )
        self.connection.execute(
            "INSERT INTO igq (story_id, channel, path, caption, publish_at) "
            "VALUES (1, 'te', 'one.mp4', 'caption', '2026-01-02')"
        )
        self.connection.commit()
        self.queue = Mock()
        self.db = types.SimpleNamespace(DB=self.connection, queue_ig=self.queue)
        self.publish = Mock(return_value="media-id")
        self.publisher = types.SimpleNamespace(publish=self.publish)

    def tearDown(self):
        self.connection.close()

    def test_existing_rows_seed_queue_guard_and_new_rows_are_unique(self):
        ig_once.install(self.db, self.publisher)

        self.assertIsNone(self.db.queue_ig(1, "te", "one.mp4", "caption", "slot"))
        self.assertIs(
            self.db.queue_ig(2, "te", "two.mp4", "caption", "slot"),
            self.queue.return_value,
        )
        self.assertIsNone(self.db.queue_ig(2, "te", "two.mp4", "caption", "slot"))

        self.queue.assert_called_once_with(2, "te", "two.mp4", "caption", "slot")

    def test_queue_guard_is_removed_if_queueing_fails(self):
        self.queue.side_effect = RuntimeError("queue failed")
        ig_once.install(self.db, self.publisher)

        with self.assertRaisesRegex(RuntimeError, "queue failed"):
            self.db.queue_ig(3, "te", "three.mp4", "caption", "slot")

        self.queue.side_effect = None
        self.db.queue_ig(3, "te", "three.mp4", "caption", "slot")
        self.assertEqual(self.queue.call_count, 2)

    def test_publish_suppresses_successful_repeat_but_allows_retry_after_error(self):
        ig_once.install(self.db, self.publisher)
        self.publish.side_effect = RuntimeError("upload failed")

        with self.assertRaisesRegex(RuntimeError, "upload failed"):
            self.publisher.publish("te", "one.mp4", "caption", "1_te.mp4")

        self.publish.side_effect = None
        self.assertEqual(
            self.publisher.publish("te", "one.mp4", "caption", "1_te.mp4"),
            "media-id",
        )
        self.assertIsNone(
            self.publisher.publish("te", "one.mp4", "caption", "1_te.mp4")
        )
        self.assertEqual(self.publish.call_count, 2)

    def test_generic_filenames_do_not_collide_across_distinct_videos(self):
        ig_once.install(self.db, self.publisher)

        first = self.publisher.publish("hi", "/tmp/first/reel.mp4", "caption", "queued.mp4")
        second = self.publisher.publish("hi", "/tmp/second/reel.mp4", "caption", "queued.mp4")

        self.assertEqual(first, "media-id")
        self.assertEqual(second, "media-id")
        self.assertEqual(self.publish.call_count, 2)


if __name__ == "__main__":
    unittest.main()
