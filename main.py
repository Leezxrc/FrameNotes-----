import sys
import os
import traceback
from pathlib import Path


def report_exception(exc_type, exc, tb):
    try:
        folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "VideoNotes"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "startup-error.log").write_text("".join(traceback.format_exception(exc_type, exc, tb)), encoding="utf-8")
    except OSError:
        pass
    if sys.stderr is not None:
        traceback.print_exception(exc_type, exc, tb)


sys.excepthook = report_exception


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        from videonotes.worker import transcribe_job
        return transcribe_job(Path(sys.argv[2]))
    from videonotes.ui import run
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
