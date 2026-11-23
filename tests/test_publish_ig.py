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

    def test_upload_reel_sends_temp_url_to_make_webhook(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = pathlib.Path(temp_dir) / "reel.mp4"
            video.write_bytes(b"video")
            temp_upload = Mock()
            temp_upload.json.return_value = {
                "data": {"url": "https://tmpfiles.org/123/reel.mp4"}
            }
            webhook_response = Mock(status_code=200)

            with (
                patch.object(
                    publish_ig, "MAKE_WEBHOOK_URL", "https://make.example/hook"
                ),
                patch.object(
                    publish_ig.requests,
                    "post",
                    side_effect=[temp_upload, webhook_response],
                ) as post,
            ):
                result = publish_ig.upload_reel(video, "caption", "hi")

        self.assertTrue(result)
        temp_upload.raise_for_status.assert_called_once()
        post.assert_any_call(
            "https://make.example/hook",
            json={
                "video_url": "https://tmpfiles.org/dl/123/reel.mp4",
                "caption": "caption",
                "lang": "hi",
            },
            timeout=30,
        )

    def test_upload_reel_fails_without_make_webhook(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = pathlib.Path(temp_dir) / "reel.mp4"
            video.write_bytes(b"video")

            with patch.object(publish_ig, "MAKE_WEBHOOK_URL", ""), patch.object(
                publish_ig.requests, "post"
            ) as post:
                result = publish_ig.upload_reel(video, "caption", "hi")

        self.assertFalse(result)
        post.assert_not_called()

    def test_upload_reel_reports_make_webhook_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = pathlib.Path(temp_dir) / "reel.mp4"
            video.write_bytes(b"video")
            temp_upload = Mock()
            temp_upload.json.return_value = {
                "data": {"url": "https://tmpfiles.org/123/reel.mp4"}
            }
            webhook_response = Mock(status_code=500, text="failed")

            with (
                patch.object(
                    publish_ig, "MAKE_WEBHOOK_URL", "https://make.example/hook"
                ),
                patch.object(
                    publish_ig.requests,
                    "post",
                    side_effect=[temp_upload, webhook_response],
                ),
            ):
                result = publish_ig.upload_reel(video, "caption", "hi")

        self.assertFalse(result)

    def test_upload_reel_fails_on_invalid_temp_host_response(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = pathlib.Path(temp_dir) / "reel.mp4"
            video.write_bytes(b"video")
            temp_upload = Mock()
            temp_upload.json.return_value = {"data": {}}

            with (
                patch.object(
                    publish_ig, "MAKE_WEBHOOK_URL", "https://make.example/hook"
                ),
                patch.object(
                    publish_ig.requests, "post", return_value=temp_upload
                ) as post,
            ):
                result = publish_ig.upload_reel(video, "caption", "hi")

        self.assertFalse(result)
        post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
