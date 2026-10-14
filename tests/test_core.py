import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from videonotes.core import (Project, Segment, atomic_write, export_text, load_project,
                             save_project, timestamp, validate_segments)


class ProjectTests(unittest.TestCase):
    def test_timestamp_rounding_and_long_video(self):
        self.assertEqual(timestamp(59.9996, True), "00:01:00,000")
        self.assertEqual(timestamp(3661.25, True), "01:01:01,250")

    def test_bad_timestamps_and_input(self):
        for start, end in [(float("nan"), 2), (0, float("inf")), (-1, 1), (2, 1), (0, 0), (True, 1)]:
            with self.assertRaises(ValueError):
                validate_segments([{"start": start, "end": end, "text": "test"}])
        with self.assertRaises(ValueError):
            validate_segments("not a list")

    def test_project_roundtrip_relative_unicode_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = Project(str(root / "中文 video.mp4"), [Segment(0.1, 2.2, "你好\nworld")], "笔记")
            target = root / "课程.vnotes.json"
            save_project(target, project)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["video"], "中文 video.mp4")
            self.assertEqual(load_project(target), project)

    def test_atomic_failure_preserves_original(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "notes.txt"
            atomic_write(target, "old")
            with patch("videonotes.core.os.replace", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    atomic_write(target, "new")
            self.assertEqual(target.read_text(), "old")
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_export_contents_and_srt_blocks(self):
        project = Project("video.mp4", [Segment(0, 1.5, "你好\n\n世界"), Segment(2, 3, "Hello")], "重点")
        srt = export_text(project, "srt")
        self.assertIn("00:00:00,000 --> 00:00:01,500", srt)
        self.assertIn("你好\n世界\n\n2\n", srt)
        self.assertNotIn("重点", srt)
        self.assertIn("重点", export_text(project, "txt"))
        self.assertIn("**00:00:02.000**", export_text(project, "md"))


if __name__ == "__main__":
    unittest.main()
