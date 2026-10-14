"""Real local-video recognition, decoding and export checks. Run from project root."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from videonotes.core import Project, atomic_write, export_text, load_project, save_project
from videonotes.ui import MainWindow, STYLE

app = QApplication([])
app.setOrganizationName("VideoNotes")
app.setApplicationName("VideoNotes")
app.setFont(QFont("Microsoft YaHei UI", 10))
app.setStyle("Fusion")
app.setStyleSheet(STYLE)
window = MainWindow()
failures = []
window.error = lambda title, detail: failures.append(f"{title}: {detail}")
window._set_project(Project(str(ROOT / ".test-artifacts" / "demo.mp4")))
window.notes.setPlainText("测试笔记：本地视频识别、字幕校对、导出与项目恢复。")
window.show()
window.player.play()
window.start_job()
deadline = time.monotonic() + 180
while window.process is not None and time.monotonic() < deadline:
    app.processEvents()
    time.sleep(0.02)
if window.process is not None:
    window.cancel_job()
    window.process.waitForFinished(3000)
    raise RuntimeError("Recognition timeout")
assert not failures, failures
assert window.project.segments, "No speech recognized"
assert "video" in " ".join(item.text for item in window.project.segments).lower()
assert window.player.duration() > 1000, "Player failed to decode video"
window.player.pause()
window.player.setPosition(1500)
app.processEvents()
output = ROOT / ".test-artifacts"
for kind in ("srt", "txt", "md"):
    atomic_write(output / f"demo.{kind}", export_text(window.project, kind))
save_project(output / "demo.vnotes.json", window.project)
assert load_project(output / "demo.vnotes.json") == window.project
window._position(1500)
window.grab().save(str(output / "preview.png"))
print("REAL VIDEO PASS:", len(window.project.segments), "segments; duration_ms=", window.player.duration())
print("TRANSCRIPT:", " ".join(item.text for item in window.project.segments))
window.dirty = False
window.close()
app.processEvents()
