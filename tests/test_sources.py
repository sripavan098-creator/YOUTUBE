import unittest

from pipeline import sources


class SourceRelevanceTests(unittest.TestCase):
    def test_channel_focus_terms_add_specificity_score(self):
        channels = {
            "hi": {"focus_terms": ["smartphone", "UPI"]},
            "te": {"focus_terms": ["Hyderabad", "local jobs"]},
        }

        scores = sources._channel_scores(
            "New smartphone payment features arrive in Hyderabad", channels
        )

        self.assertEqual(scores, {"hi": 2, "te": 2})


if __name__ == "__main__":
    unittest.main()
