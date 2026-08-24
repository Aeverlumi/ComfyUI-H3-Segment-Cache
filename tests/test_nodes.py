import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

import nodes


def has_ffmpeg():
    try:
        return bool(shutil.which("ffmpeg") or nodes._ffmpeg())
    except RuntimeError:
        return False


class FolderPathsStub:
    def __init__(self, root):
        self.output = Path(root) / "output's"
        self.temp = Path(root) / "temp"

    def get_output_directory(self):
        return str(self.output)

    def get_temp_directory(self):
        return str(self.temp)


class SegmentCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_folder_paths = nodes.folder_paths
        nodes.folder_paths = FolderPathsStub(self.temp_dir.name)

    def tearDown(self):
        nodes.folder_paths = self.original_folder_paths
        self.temp_dir.cleanup()

    @staticmethod
    def frames(value):
        return np.full((4, 24, 32, 3), value, dtype=np.float32)

    @staticmethod
    def audio():
        return {
            "waveform": np.zeros((1, 1, 4000), dtype=np.float32),
            "sample_rate": 8000,
        }

    def test_public_node_names(self):
        self.assertIn("H3SegmentCacheFinalize", nodes.NODE_CLASS_MAPPINGS)
        self.assertNotIn("H3SegmentCacheFinalizeV2", nodes.NODE_CLASS_MAPPINGS)

    def test_handoff_splits_frames_and_audio(self):
        images = self.frames(0.25)
        before, audio, selected, index = nodes.H3FrameHandoff().split(
            images, self.audio(), frame_index=2, fps=8.0
        )
        self.assertEqual(index, 2)
        self.assertEqual(before.shape[0], 2)
        self.assertEqual(selected.shape[0], 1)
        self.assertEqual(audio["waveform"].shape[-1], 2000)

    def test_invalid_cache_token_is_rejected(self):
        with self.assertRaises(ValueError):
            nodes._cache_dir("../../outside")

    @unittest.skipUnless(has_ffmpeg(), "FFmpeg unavailable")
    def test_encode_append_finalize_and_preview(self):
        settings = {
            "fps": 8.0,
            "format": "video/h264-mp4",
            "pix_fmt": "yuv444p",
            "crf": 0,
            "preset": "fast",
            "audio_bitrate": "192k",
            "trim_to_audio": False,
        }
        token = nodes.H3SegmentCacheStart().start(
            self.frames(0.1), self.audio(), **settings
        )[0]
        nodes.H3SegmentCacheAppend().append(
            token, 1, self.frames(0.8), self.audio(), **settings
        )

        response = nodes.H3SegmentCacheFinalize().finalize(
            token,
            "integration_test",
            format="video/h264-mp4",
            pix_fmt="yuv420p",
            crf=22,
            preset="medium",
            audio_bitrate="192k",
            trim_to_audio=False,
            save_output=True,
        )

        preview = response["ui"]["gifs"][0]
        output_path = Path(response["result"][0][1][0])
        self.assertTrue(output_path.is_file())
        self.assertGreater(output_path.stat().st_size, 0)
        self.assertEqual(preview["filename"], output_path.name)
        self.assertEqual(preview["subfolder"], "h3_long_video")
        self.assertEqual(preview["type"], "output")
        self.assertFalse(nodes._cache_dir(token).exists())


if __name__ == "__main__":
    unittest.main()
