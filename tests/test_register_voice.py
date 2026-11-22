import base64
import os
import pathlib
import tempfile
import unittest
from unittest.mock import Mock, patch

from pipeline import register_voice, sarvam_voice, tts


def api_response(payload):
    response = Mock()
    response.ok = True
    response.status_code = 200
    response.text = ""
    response.json.return_value = payload
    return response


class RegisterVoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_prefers_named_sample_in_voice_samples(self):
        sample_dir = self.root / "assets" / "voice_samples"
        sample_dir.mkdir(parents=True)
        expected = sample_dir / "my_voice.wav"
        expected.write_bytes(b"sample")
        (self.root / "my_voice.wav").write_bytes(b"root sample")

        self.assertEqual(register_voice.find_voice_sample(self.root), expected)

    @patch("pipeline.register_voice.requests.post")
    def test_registers_sarvam_using_voice_create_multipart_contract(self, post):
        sample = self.root / "my_voice.wav"
        sample.write_bytes(b"sample")
        post.return_value = api_response({"data": {"voice_id": "svc-test"}})

        voice_id = register_voice.register_sarvam(sample, "api-key", "te-IN")

        self.assertEqual(voice_id, "svc-test")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://api.sarvam.ai/voices/create")
        self.assertEqual(kwargs["data"]["language"], "te-IN")
        self.assertEqual(kwargs["files"]["file"][0], "my_voice.wav")
        self.assertNotIn("Content-Type", kwargs["headers"])

    @patch("pipeline.register_voice.requests.post")
    def test_registers_google_with_separate_source_and_consent_audio(self, post):
        sample = self.root / "my_voice.wav"
        consent = self.root / "consent.wav"
        sample.write_bytes(b"source")
        consent.write_bytes(b"consent")
        post.return_value = api_response({"id": "voice-test"})

        voice_id = register_voice.register_gemini(sample, consent, "api-key")

        self.assertEqual(voice_id, "voice-test")
        body = post.call_args.kwargs["json"]
        replicated = body["voice"]["replicated"]
        self.assertEqual(body["voice"]["type"], "replicated")
        self.assertEqual(
            replicated["source_audio"]["data"],
            base64.b64encode(b"source").decode("ascii"),
        )
        self.assertEqual(
            replicated["consent_audio"]["data"],
            base64.b64encode(b"consent").decode("ascii"),
        )
        self.assertEqual(replicated["consent_audio"]["mime_type"], "audio/wav")

    def test_rejects_reusing_sample_as_google_consent_audio(self):
        sample = self.root / "my_voice.wav"
        sample.write_bytes(b"sample")

        with self.assertRaisesRegex(ValueError, "separate recording"):
            register_voice.register_gemini(sample, sample, "api-key")

    @patch("pipeline.sarvam_voice.SarvamAI")
    def test_sarvam_voice_registration_uses_sdk(self, sarvam_ai):
        sample = self.root / "my_voice.wav"
        sample.write_bytes(b"sample")
        client = sarvam_ai.return_value
        client.voice_cloning.create_voice.return_value.data.voice_id = "svc-test"
        cache_file = self.root / "sarvam_voice_cache.json"

        with patch.dict(os.environ, {"SARVAM_API_KEY": "api-key"}), patch.object(
            sarvam_voice, "_CACHE_FILE", cache_file
        ):
            voice_id = sarvam_voice.register_voice(sample, "te")

        self.assertEqual(voice_id, "svc-test")
        kwargs = client.voice_cloning.create_voice.call_args.kwargs
        self.assertEqual(kwargs["name"], "my-cloned-voice")
        self.assertEqual(kwargs["language"], "te-IN")
        self.assertEqual(kwargs["style"], "conversational")
        self.assertTrue(kwargs["remove_background_noise"])

    @patch("pipeline.sarvam_voice.subprocess.run")
    @patch("pipeline.sarvam_voice.SarvamAI")
    def test_sarvam_cloned_id_uses_sdk_and_saves_wav(self, sarvam_ai, run):
        output = self.root / "speech.wav"
        audio = base64.b64encode(b"wav audio").decode("ascii")
        client = sarvam_ai.return_value
        client.voice_cloning.convert.return_value = Mock(
            audio_b64=audio, audio=None
        )
        run.return_value.stdout = "1.25"

        with patch.dict(os.environ, {"SARVAM_API_KEY": "api-key"}):
            duration = sarvam_voice.synth_sarvam(
                "నమస్తే", "te", str(output), voice_id="svc-test"
            )

        self.assertEqual(duration, 1.25)
        client.voice_cloning.convert.assert_called_once_with(
            voice_id="svc-test",
            text="నమస్తే",
            language_code="te-IN",
            pace=1.15,
            output_audio_codec="wav",
        )
        self.assertEqual(output.read_bytes(), b"wav audio")

    @patch("pipeline.register_voice.register_gemini", return_value="voice-test")
    @patch("pipeline.register_voice.find_voice_sample")
    @patch("pipeline.register_voice.load_dotenv")
    def test_main_defaults_google_consent_audio_to_consent_wav(
        self, load_dotenv, find_sample, register_gemini
    ):
        sample_dir = self.root / "assets" / "voice_samples"
        sample_dir.mkdir(parents=True)
        consent = sample_dir / "consent.wav"
        consent.write_bytes(b"consent")
        sample = sample_dir / "my_voice.wav"
        find_sample.return_value = sample

        with patch.object(register_voice, "ROOT", self.root), patch.dict(
            os.environ, {"GEMINI_API_KEY": "api-key"}, clear=True
        ):
            self.assertEqual(register_voice.main(), 0)

        register_gemini.assert_called_once_with(sample, consent, "api-key")

    @patch("pipeline.tts.requests.post")
    def test_sarvam_cloned_id_uses_clone_endpoint(self, post):
        output = self.root / "speech.wav"
        audio = base64.b64encode(b"wav audio").decode("ascii")
        post.return_value = api_response({"audio_b64": audio})

        with patch.object(tts, "SARVAM_API_KEY", "api-key"), patch.dict(
            tts.SARVAM_VOICES, {"te": "svc-test"}
        ):
            tts._sarvam_tts("నమస్తే", "te", output)

        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://api.sarvam.ai/voices/clone")
        self.assertEqual(kwargs["data"]["voice_id"], "svc-test")
        self.assertNotIn("json", kwargs)
        self.assertEqual(output.read_bytes(), b"wav audio")


if __name__ == "__main__":
    unittest.main()
