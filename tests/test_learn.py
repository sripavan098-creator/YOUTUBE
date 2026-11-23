import unittest
from unittest.mock import Mock, patch

from pipeline import learn
from pipeline import publish_yt
from pipeline.scripts import HOOK_ARCHETYPES


class LearnTests(unittest.TestCase):
    def test_refresh_stats_saves_retention_metrics_when_available(self):
        youtube = Mock()
        youtube.videos.return_value.list.return_value.execute.return_value = {
            "items": [{
                "id": "video-id",
                "statistics": {"viewCount": "120", "likeCount": "8", "commentCount": "2"},
            }]
        }
        analytics = Mock()
        analytics.reports.return_value.query.return_value.execute.return_value = {
            "rows": [["video-id", 90, 75.5, 23.0, 3]]
        }

        with patch.object(
            learn.db, "uploaded_stories",
            return_value=[(1, "hi", "video-id", "stake", "explainer", "2026-11-20")],
        ), patch.object(learn.db, "save_perf") as save_perf, patch.object(
            publish_yt, "_service", return_value=youtube
        ), patch.object(publish_yt, "_analytics_service", return_value=analytics):
            self.assertEqual(learn.refresh_stats(), 1)

        save_perf.assert_called_once_with(
            1, "hi", "stake", "explainer", 120, 8, 2,
            engaged_views=90, average_view_percentage=75.5,
            average_view_duration=23.0, subscribers_gained=3,
        )

    def test_prefers_retention_over_raw_views_when_available(self):
        retention = {
            "stake": 30,
            "secret": 35,
            "number": 40,
            "question": 85,
            "contrarian": 50,
            "countdown": 60,
        }
        rows = [
            (archetype, "explainer", 10000 if archetype != "question" else 10,
             0, 0, 50, score, 10.0, 0)
            for archetype, score in retention.items()
        ]

        with patch.object(learn.db, "perf_rows", return_value=rows), \
                patch.object(learn.random, "random", return_value=0.99):
            selected = learn.pick_archetype("hi")

        self.assertEqual(selected, "question")

    def test_falls_back_to_views_for_existing_stats_without_retention(self):
        rows = [
            (archetype, "explainer", views, 0, 0, None, None, None, None)
            for archetype, views in zip(HOOK_ARCHETYPES, [10, 20, 30, 40, 100, 50])
        ]

        with patch.object(learn.db, "perf_rows", return_value=rows), \
                patch.object(learn.random, "random", return_value=0.99):
            selected = learn.pick_archetype("hi")

        self.assertEqual(selected, "contrarian")


if __name__ == "__main__":
    unittest.main()
