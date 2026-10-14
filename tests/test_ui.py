import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from videonotes.core import Project, Segment, write_json
from videonotes.ui import MainWindow, STYLE

APP = QApplication.instance() or QApplication([])
APP.setStyleSheet(STYLE)


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow()
        self.window._set_project(Project(segments=[Segment(1, 2, "你好世界"), Segment(3, 4, "Second line")]))

    def tearDown(self):
        self.window.dirty = False
        self.window.close()
        APP.processEvents()

    def test_edit_search_copy_and_playback_sync(self):
        window = self.window
        window.model.setData(window.model.index(0, 1), "修改字幕")
        self.assertTrue(window.dirty)
        self.assertEqual(window.project.segments[0].text, "修改字幕")
        window.search.setText("Second")
        self.assertEqual(window.proxy.rowCount(), 1)
        window.copy_transcript()
        self.assertEqual(APP.clipboard().text(), "修改字幕\nSecond line")
        window._position(1500)
        self.assertEqual(window.caption.text(), "修改字幕")
        window._position(2500)
        self.assertEqual(window.caption.text(), "")
        window.notes.setPlainText("学习笔记")
        self.assertEqual(window.project.notes, "学习笔记")

    def test_cancel_and_empty_result_preserve_previous_subtitles(self):
        window = self.window
        for cancelled in [True, False]:
            window.job_dir = tempfile.TemporaryDirectory()
            write_json(Path(window.job_dir.name) / "result.json", {"segments": [], "language": "en"})
            window.cancelled = cancelled
            window._finished(0, None)
            self.assertEqual(window.project.segments[0].text, "你好世界")

    def test_valid_result_commits_but_preserves_notes(self):
        window = self.window
        window.notes.setPlainText("Keep me")
        window.job_dir = tempfile.TemporaryDirectory()
        write_json(Path(window.job_dir.name) / "result.json", {
            "segments": [{"start": 0, "end": 1, "text": "new result"}], "language": "en"})
        window._finished(0, None)
        self.assertEqual(window.project.segments[0].text, "new result")
        self.assertEqual(window.project.notes, "Keep me")
        self.assertTrue(window.dirty)

    def test_failure_preserves_transcript(self):
        window = self.window
        window.job_dir = tempfile.TemporaryDirectory()
        write_json(Path(window.job_dir.name) / "error.json", {"message": "unsupported audio"})
        with patch.object(window, "error") as error:
            window._finished(1, None)
            error.assert_called_once()
        self.assertEqual(len(window.project.segments), 2)


if __name__ == "__main__":
    unittest.main()
