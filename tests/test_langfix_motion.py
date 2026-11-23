import pathlib
import tempfile
import unittest
from unittest.mock import Mock, patch

from pipeline import langfix, motion


class LangfixTests(unittest.TestCase):
    def test_glossary_adds_source_terms_and_known_acronyms(self):
        terms = langfix.glossary({
            "title": "FSSAI tests water",
            "body": "The FSSAI found Bromate in a bottle.",
        })
        self.assertIn("FSSAI", terms)
        self.assertIn("Bromate", terms)

    def test_cer_measures_text_difference(self):
        self.assertEqual(langfix._cer("hello", "hello"), 0.0)
        self.assertEqual(langfix._cer("helo", "hello"), 0.2)
        self.assertEqual(langfix._cer("", "hello"), 1.0)

    def test_audio_gate_returns_transcription_and_cer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            mp3 = pathlib.Path(temp_dir) / "voice.mp3"
            mp3.write_bytes(b"audio")
            response = Mock(status_code=200)
            response.json.return_value = {"text": "hello"}
            with patch.dict(
                langfix.os.environ,
                {"ASR_GATE": "1", "GROQ_API_KEY": "test-key"},
            ), patch("requests.post", return_value=response):
                cer, heard = langfix.audio_gate(str(mp3), "hello", "en")

        self.assertEqual(cer, 0.0)
        self.assertEqual(heard, "hello")


class MotionTests(unittest.TestCase):
    def test_motion_fallback_returns_copied_still(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            src = root / "photo.jpg"
            src.write_bytes(b"jpg")
            dst = root / "shot.mp4"
            with patch("pipeline.motion.subprocess.run",
                       side_effect=RuntimeError("ffmpeg failed")):
                result = motion.still_to_clip(src, dst, 3.0)
            self.assertEqual(result.suffix, ".jpg")
            self.assertTrue(result.exists())


    def test_audio_enhancement_disabled_by_default(self):
        with patch.dict(motion.os.environ, {"AUDIO_ENHANCE": "0"}):
            self.assertEqual(
                motion.enhance_audio("voice.mp3", [0.0, 2.0], "enhanced.mp3"),
                "voice.mp3",
            )


if __name__ == "__main__":
    unittest.main()
