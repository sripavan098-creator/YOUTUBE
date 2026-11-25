import unittest

from pipeline import flowfix, main, retention


class FlowfixTests(unittest.TestCase):
    def test_telugu_normalization_preserves_hook_bounds_and_concrete_unique_shots(self):
        beats = [
            {"line": "మీరు phone update ధర చూడండి ఇప్పుడు?", "shot": "phone"},
            {"line": "కొత్త update వల్ల ధర మారుతుంది", "shot": "phone"},
            {"line": "ఇది మూడు నెలల తర్వాత అమలవుతుంది", "shot": "phone"},
            {"line": "కంపెనీ కొత్త వివరాలు వెల్లడించింది", "shot": "phone"},
            {"line": "అందుకే మీ ఎంపిక మారవచ్చు", "shot": "phone"},
            {"line": "మీరు ఏది ఎంచుకుంటారు చెప్పండి?", "shot": "phone"},
        ]
        script = {"beats": beats}

        flowfix.normalize(script, "te")

        self.assertGreaterEqual(len(script["beats"][0]["line"].split()), flowfix.HOOK_MIN)
        self.assertLessEqual(len(script["beats"][0]["line"].split()), flowfix.HOOK_MAX)
        shots = [beat["shot"] for beat in script["beats"]]
        self.assertEqual(len(shots), len(set(shots)))
        for shot in shots:
            self.assertTrue(retention.shot_ok(shot)[0], shot)

    def test_known_telugu_loanword_is_not_flagged(self):
        self.assertEqual(flowfix.smart_gibberish("స్క్రీన్", "te"), [])

    def test_one_run_channel_filter_does_not_change_default(self):
        self.assertIsNone(main._channel_filter_from_args(["--now"]))
        self.assertEqual(main._channel_filter_from_args(["--now", "--only", "te"]), {"te"})
        with self.assertRaises(SystemExit):
            main._channel_filter_from_args(["--now", "--only", "unknown"])


if __name__ == "__main__":
    unittest.main()
