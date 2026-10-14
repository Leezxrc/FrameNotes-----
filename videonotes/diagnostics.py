"""Optional packaged end-to-end smoke test, activated only by --self-test DIR."""
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from .core import Project, atomic_write, export_text, load_project, save_project, write_json


def schedule(window, folder: Path):
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    state = {"frames": 0, "started": time.monotonic(), "errors": [], "done": False}
    window.audio.setVolume(0)
    window.error = lambda title, detail: state["errors"].append(f"{title}: {detail}")
    window.video.videoSink().videoFrameChanged.connect(
        lambda frame: state.update(frames=state["frames"] + int(frame.isValid())))
    window._set_project(Project(str(folder / "demo.mp4")))
    window.notes.setPlainText("学习笔记：播放、字幕识别、文字导出与项目保存。")

    def finish(error=None):
        if state["done"]:
            return
        state["done"] = True
        check.stop()
        if window.process is not None:
            window.cancel_job()
            window.process.waitForFinished(3000)
        write_json(folder / "packaged-report.json", {"ok": error is None, "error": error,
            "frames": state["frames"], "duration_ms": window.player.duration(),
            "segments": len(window.project.segments),
            "transcript": " ".join(item.text for item in window.project.segments)})
        window.dirty = False
        window.close()
        QApplication.instance().exit(0 if error is None else 1)

    def poll():
        if state["errors"]:
            finish("; ".join(state["errors"]))
        elif time.monotonic() - state["started"] > 120:
            finish("Smoke test timed out")
        elif window.process is None and window.project.segments and state["frames"] > 0:
            try:
                text = " ".join(row.text for row in window.project.segments).lower()
                assert "video" in text, text
                for kind in ("srt", "txt", "md"):
                    atomic_write(folder / f"packaged.{kind}", export_text(window.project, kind))
                target = folder / "packaged.vnotes.json"
                save_project(target, window.project)
                assert load_project(target) == window.project
                window.player.pause()
                window._position(1500)
                window.grab().save(str(folder / "packaged-preview.png"))
                finish()
            except Exception as exc:
                finish(str(exc))

    window.player.play()
    window.start_job()
    check = QTimer(window)
    check.setInterval(200)
    check.timeout.connect(poll)
    check.start()
