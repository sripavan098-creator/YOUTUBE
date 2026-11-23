import unittest

from pipeline import scripts


def valid_script():
    beats = [
        {"line": "This hook asks one clear question", "shot": "hook object"},
    ]
    for index in range(1, 6):
        line = " ".join(f"fact{index}_{word}" for word in range(11))
        if index == 5:
            line += "?"
        beats.append({"line": line, "shot": f"visual subject {index}"})
    return {
        "title": "A useful technology update",
        "claim": "This update changes how people use a service.",
        "supporting_facts": ["Fact one", "Fact two", "Fact three"],
        "hook_text": "A clear claim",
        "story_format": "explainer",
        "cta_text": "What would you choose?",
        "beats": beats,
        "hashtags": ["#technology"],
    }


class ScriptValidationTests(unittest.TestCase):
    def test_accepts_shared_script_specification(self):
        self.assertIsNone(scripts.check_script(valid_script()))

    def test_rejects_hook_over_six_words(self):
        script = valid_script()
        script["beats"][0]["line"] = "This hook asks one clear question today"

        self.assertIn("hook is 7 words", scripts.check_script(script))

    def test_rejects_script_outside_total_word_limit(self):
        script = valid_script()
        for index, beat in enumerate(script["beats"][1:], 1):
            beat["line"] = "five short clear factual words" + ("?" if index == 5 else ".")

        self.assertIn("script is", scripts.check_script(script))
        self.assertIn("need 60-95", scripts.check_script(script))

    def test_requires_a_supported_story_format_and_topic_specific_cta(self):
        script = valid_script()
        script["story_format"] = "random"
        self.assertEqual(
            scripts.check_script(script),
            "story_format must be explainer, list, versus, or timeline",
        )

        script["story_format"] = "explainer"
        script["cta_text"] = ""
        self.assertEqual(scripts.check_script(script), "missing topic-specific cta_text")

    def test_layout_prefers_story_format_without_recent_repetition(self):
        self.assertEqual(
            scripts.pick_layout(["list", "versus"], ["list", "explainer", "versus"],
                                preferred="explainer"),
            "explainer",
        )
        self.assertEqual(
            scripts.pick_layout(["versus", "timeline", "explainer"],
                                ["list", "explainer", "versus", "timeline"],
                                preferred="explainer"),
            "list",
        )


if __name__ == "__main__":
    unittest.main()
