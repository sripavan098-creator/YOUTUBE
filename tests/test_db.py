import sqlite3
import unittest
from unittest.mock import patch

from pipeline import db


class PerformanceStorageTests(unittest.TestCase):
    def test_missing_analytics_does_not_erase_a_prior_measurement(self):
        connection = sqlite3.connect(":memory:")
        connection.execute(
            "CREATE TABLE perf("
            "sid INTEGER PRIMARY KEY, channel TEXT, archetype TEXT, layout TEXT, "
            "views INT DEFAULT 0, likes INT DEFAULT 0, comments INT DEFAULT 0, "
            "checked_at TEXT, engaged_views INT, average_view_percentage REAL, "
            "average_view_duration REAL, subscribers_gained INT)"
        )
        try:
            with patch.object(db, "DB", connection):
                db.save_perf(
                    1, "hi", "stake", "explainer", 100, 4, 1,
                    engaged_views=80, average_view_percentage=75.0,
                    average_view_duration=12.5, subscribers_gained=2,
                )
                db.save_perf(1, "hi", "stake", "explainer", 120, 5, 2)

                row = db.perf_rows("hi")[0]
        finally:
            connection.close()

        self.assertEqual(row[2:5], (120, 5, 2))
        self.assertEqual(row[5:], (80, 75.0, 12.5, 2))


if __name__ == "__main__":
    unittest.main()
