"""Runs exclusively in a child process; exchanges files, not GUI objects."""
import os
import sys
import traceback
from dataclasses import asdict
from pathlib import Path

from .core import Segment, read_json, write_json


def transcribe_job(folder: Path) -> int:
    # Windowed PyInstaller executables have no stdout/stderr. Libraries may log.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    status = folder / "status.json"
    try:
        request = read_json(folder / "request.json")
        write_json(status, {"message": "正在加载识别引擎…", "progress": -1})
        from faster_whisper import WhisperModel
        from faster_whisper.utils import download_model

        if not Path(request["video"]).is_file():
            raise ValueError("视频文件不存在，请重新选择文件。")
        cache = request["cache"]
        write_json(status, {"message": "正在准备模型；首次使用会联网下载，请稍候…", "progress": -1})
        model_name = request["model"]
        # Reuse a model already downloaded by another compatible local application.
        try:
            model_name = download_model(model_name, local_files_only=True)
        except Exception:
            pass
        model = WhisperModel(model_name, device="cpu", compute_type="int8",
                             cpu_threads=max(1, min(8, (os.cpu_count() or 4) - 1)),
                             download_root=cache)
        write_json(status, {"message": "正在读取音轨并检测语音…", "progress": -1})
        rows, info = model.transcribe(request["video"], language=request.get("language"),
                                      beam_size=5, vad_filter=True,
                                      condition_on_previous_text=False)
        result = []
        for row in rows:
            if row.text.strip() and row.end > row.start:
                result.append(asdict(Segment(row.start, row.end, row.text.strip())))
            write_json(status, {"message": f"正在识别 · 已生成 {len(result)} 条字幕",
                                "progress": min(99, int(row.end / max(info.duration, 1) * 100)),
                                "preview": row.text.strip()})
        write_json(folder / "result.json", {"segments": result, "language": info.language})
        write_json(status, {"message": "识别完成", "progress": 100})
        return 0
    except Exception as exc:
        write_json(folder / "error.json", {"message": str(exc), "detail": traceback.format_exc()})
        return 1
