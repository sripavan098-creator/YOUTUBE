import json
import pathlib
import tempfile
import unittest
from unittest.mock import Mock, patch

from pipeline import visuals


def image_page(page_id, title, license_name, mime="image/jpeg"):
    return {
        "pageid": page_id,
        "title": title,
        "imageinfo": [{
            "mime": mime,
            "thumburl": f"https://commons.wikimedia.org/thumb/{page_id}.jpg",
            "url": f"https://commons.wikimedia.org/{page_id}.jpg",
            "descriptionurl": f"https://commons.wikimedia.org/wiki/{title}",
            "extmetadata": {"LicenseShortName": {"value": license_name}},
        }],
    }


class VisualsTests(unittest.TestCase):
    def test_candidate_relevance_requires_subject_overlap(self):
        self.assertTrue(visuals._is_relevant("Bisleri water bottle", "water bottle on table"))
        self.assertFalse(visuals._is_relevant("Bisleri water bottle", "old soldier poster"))
        self.assertTrue(visuals._is_relevant("new smartphone launch", "smartphone on display"))
        self.assertTrue(visuals._is_relevant("नया स्मार्टफोन", "स्मार्टफोन का चित्र"))

    def test_wikimedia_search_uses_cached_public_domain_results(self):
        response = Mock()
        response.json.return_value = {
            "query": {"pages": [
                image_page(1, "File:Free.jpg", "CC0"),
                image_page(2, "File:BY.jpg", "CC BY-SA 4.0"),
                image_page(3, "File:Public.jpg", "Public domain", "image/png"),
            ]}
        }

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            visuals, "WIKIMEDIA_CACHE", pathlib.Path(temp_dir) / "cache.json"
        ), patch.object(visuals.requests, "get", return_value=response) as get:
            visuals.WIKIMEDIA_CACHE.write_text(
                json.dumps({"smartphone India": []}), encoding="utf-8"
            )
            results = visuals._wikimedia_search("smartphone India")
            cached_results = visuals._wikimedia_search("smartphone India")

        self.assertEqual([photo["id"] for photo in results], [1, 3])
        self.assertEqual(results, cached_results)
        self.assertEqual(results[1]["extension"], ".png")
        get.assert_called_once()

    def test_fetch_shots_uses_wikimedia_when_unsplash_returns_nothing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            expected = pathlib.Path(temp_dir) / "0.jpg"
            with patch.object(visuals, "_unsplash_photo", return_value=None), patch.object(
                visuals, "_wikimedia_photo", return_value=str(expected)
            ) as wikimedia, patch.object(visuals, "_pexels_video") as pexels:
                paths = visuals.fetch_shots(
                    ["smartphone India"], pathlib.Path(temp_dir) / "shots"
                )

        self.assertEqual(paths, [str(expected)])
        wikimedia.assert_called_once()
        pexels.assert_not_called()

    def test_fetch_shots_never_uses_unrelated_generic_fallbacks(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            visuals, "_unsplash_photo", return_value=None
        ) as unsplash, patch.object(
            visuals, "_wikimedia_photo", return_value=None
        ) as wikimedia, patch.object(visuals, "_pexels_video", return_value=None) as pexels:
            paths = visuals.fetch_shots(
                ["soldier poster"], pathlib.Path(temp_dir) / "shots"
            )

        self.assertEqual(paths, [None])
        self.assertEqual(
            [call.args[0] for call in unsplash.call_args_list],
            ["soldier poster", "soldier poster India"],
        )
        self.assertEqual(
            [call.args[0] for call in wikimedia.call_args_list],
            ["soldier poster", "soldier poster India"],
        )
        self.assertEqual(
            [call.args[0] for call in pexels.call_args_list],
            ["soldier poster", "soldier poster India"],
        )


if __name__ == "__main__":
    unittest.main()
