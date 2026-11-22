import os
import pathlib
import tempfile
import unittest
from unittest.mock import Mock, patch

from pipeline import publish_ig


class PublishInstagramTests(unittest.TestCase):
    def test_publish_uploads_reel_and_returns_media_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = pathlib.Path(temp_dir) / "reel.mp4"
            video.write_bytes(b"video")
            client = Mock()
            client.clip_upload.return_value.pk = 123

            with patch.dict(
                os.environ,
                {"IG_USER_HI": "test-user", "IG_PASS_HI": "test-password"},
                clear=True,
            ), patch.object(publish_ig, "Client", return_value=client):
                media_id = publish_ig.publish("hi", video, "caption", "queued.mp4")

        self.assertEqual(media_id, "123")
        client.login.assert_called_once_with("test-user", "test-password")
        client.clip_upload.assert_called_once_with(path=video, caption="caption")

    @patch("pipeline.publish_ig.Client")
    def test_publish_rejects_missing_video_before_login(self, client):
        with self.assertRaises(FileNotFoundError):
            publish_ig.publish("hi", "/missing/reel.mp4", "caption")

        client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
