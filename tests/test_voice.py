import unittest
from unittest.mock import patch

from pipeline import sarvam_voice, voice


class VoiceTimingTests(unittest.TestCase):
    def test_estimated_word_timings_leave_only_small_edge_margins(self):
        words = voice._estimate_word_times("one two three", 4.0)

        self.assertLessEqual(words[0]["start"], 0.02)
        self.assertGreaterEqual(words[-1]["end"], 3.97)

    def test_beat_gaps_are_brief(self):
        self.assertEqual(voice.GAP_BEFORE["fact"], 0.04)
        self.assertLessEqual(voice.GAP_BEFORE["payoff"], 0.2)

    def test_sarvam_pace_is_fast_enough_for_short_form(self):
        self.assertEqual(voice._sarvam_pace("+14%"), 1.44)
        self.assertEqual(voice._sarvam_pace("+80%"), 1.8)

    def test_sarvam_uses_configured_language_voice(self):
        with patch.dict("os.environ", {"SARVAM_VOICE_TE": "svc-test"}, clear=True):
            self.assertEqual(sarvam_voice._voice_for("te"), "svc-test")

    def test_explicit_cloned_voice_takes_precedence_over_environment(self):
        with patch.dict("os.environ", {"SARVAM_VOICE_TE": "configured"}, clear=True):
            self.assertEqual(sarvam_voice._voice_for("te", "svc-cloned"), "svc-cloned")


if __name__ == "__main__":
    unittest.main()
