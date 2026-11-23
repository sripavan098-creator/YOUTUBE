import unittest
from unittest.mock import patch
import os
import requests

from pipeline import scripts
from pipeline import retention


def valid_script():
    beats = [
        {"line": "This hook asks one clear question?", "shot": "hook object",
         "role": "hook"},
    ]
    for index in range(1, 6):
        line = " ".join(f"fact{index}_{word}" for word in range(9))
        if index == 5:
            line += "?"
        role = "rehook" if index == 3 else "payoff" if index == 5 else "fact"
        beat = {"line": line, "shot": f"visual subject {index}", "role": role}
        if index == 2:
            beat["stat"] = "₹2"
        beats.append(beat)
    return {
        "title": "A useful technology update",
        "claim": "This update changes how people use a service.",
        "supporting_facts": ["Fact one", "Fact two", "Fact three"],
        "hook_text": "A clear claim",
        "story_format": "explainer",
        "cta_text": "What would you choose?",
        "cta_screen": "5 brand list - bio link",
        "beats": beats,
        "hashtags": ["#technology"],
    }


class ScriptValidationTests(unittest.TestCase):
    def test_groq_uses_backup_key_after_primary_failure(self):
        class Completions:
            def __init__(self, text=None, error=None):
                self.text = text
                self.error = error

            def create(self, **kwargs):
                if self.error:
                    raise self.error
                class Choice:
                    message = type("Message", (), {"content": "backup response"})()
                class Response:
                    choices = [Choice()]
                return Response()

        class Client:
            def __init__(self, text=None, error=None):
                self.chat = type("Chat", (), {"completions": Completions(text, error)})()

        response = type("Response", (), {"status_code": 429})()
        primary_error = requests.HTTPError("rate limited")
        primary_error.response = response

        with patch.dict(os.environ, {
            "GROQ_API_KEY": "primary-test-key",
            "GROQ_API_KEY_2": "backup-test-key",
        }, clear=True), patch.object(scripts, "_with_retry",
                                    lambda fn, **kwargs: fn()), patch.object(
                                        scripts, "OpenAI",
                                        side_effect=[Client(error=primary_error),
                                                     Client(text="backup response")]) as openai:
            result = scripts._groq("system", "prompt", "openai/gpt-oss-120b")

        self.assertEqual(result, "backup response")
        self.assertEqual(openai.call_count, 2)
        self.assertEqual(openai.call_args_list[0].kwargs["api_key"], "primary-test-key")
        self.assertEqual(openai.call_args_list[1].kwargs["api_key"], "backup-test-key")

    def test_gemini_uses_backup_key_after_primary_rate_limit(self):
        primary = type("Response", (), {
            "status_code": 429,
            "raise_for_status": lambda self: (_ for _ in ()).throw(
                requests.HTTPError("rate limited", response=self)),
        })()
        backup = type("Response", (), {
            "status_code": 200,
            "raise_for_status": lambda self: None,
            "json": lambda self: {"candidates": [{"content": {"parts": [
                {"text": "backup response"}
            ]}}]},
        })()

        with patch.dict(os.environ, {
            "GEMINI_API_KEY": "primary-test-key",
            "GEMINI_API_KEY_2": "backup-test-key",
        }, clear=True), patch.object(scripts, "_with_retry",
                                    lambda fn, **kwargs: fn()), patch.object(
                                        scripts.requests, "post",
                                        side_effect=[primary, backup]) as post:
            result = scripts._gemini("system", "prompt", "test-model")

        self.assertEqual(result, "backup response")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(
            post.call_args_list[0].kwargs["headers"]["x-goog-api-key"],
            "primary-test-key",
        )
        self.assertEqual(
            post.call_args_list[1].kwargs["headers"]["x-goog-api-key"],
            "backup-test-key",
        )

    def test_retention_rejects_bad_visual_and_missing_number_card(self):
        script = valid_script()
        script["beats"][2]["shot"] = "future market"
        reason = retention.gates(script, "te")
        self.assertIn("abstract word", reason)

        script = valid_script()
        for beat in script["beats"]:
            beat.pop("stat", None)
        reason = retention.gates(script, "te")
        self.assertIn("no number card", reason)

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
        self.assertIn("need 50-80", scripts.check_script(script))

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
