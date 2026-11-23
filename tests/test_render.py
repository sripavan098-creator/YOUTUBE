import pathlib
import tempfile
import unittest
from unittest.mock import Mock, patch

from pipeline import render


class RenderVisualTests(unittest.TestCase):
    def test_missing_visual_is_not_decodable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = pathlib.Path(temp_dir) / "missing.jpg"
            with patch.object(render.subprocess, "run") as run:
                self.assertFalse(render._decodable_visual(missing))
            run.assert_not_called()

    def test_visual_must_decode_a_frame(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image = pathlib.Path(temp_dir) / "image.jpg"
            image.write_bytes(b"image")
            with patch.object(render.subprocess, "run", return_value=Mock(returncode=0)) as run:
                self.assertTrue(render._decodable_visual(image))
                self.assertIn("-frames:v", run.call_args.args[0])

            with patch.object(render.subprocess, "run", return_value=Mock(returncode=1)):
                self.assertFalse(render._decodable_visual(image))

    def test_frame_ranges_cover_the_video_without_overlap(self):
        self.assertEqual(
            render._frame_ranges(401, chunk_frames=180),
            [(0, 179), (180, 359), (360, 400)],
        )

    def test_default_render_chunks_are_limited_to_one_second(self):
        self.assertEqual(
            render._frame_ranges(61),
            [(0, 29), (30, 59), (60, 60)],
        )


if __name__ == "__main__":
    unittest.main()
