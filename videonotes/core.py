from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Project:
    video: str = ""
    segments: list[Segment] = field(default_factory=list)
    notes: str = ""


def timestamp(seconds: float, srt: bool = False) -> str:
    total = max(0, round(seconds * 1000))
    hours, total = divmod(total, 3_600_000)
    minutes, total = divmod(total, 60_000)
    secs, millis = divmod(total, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{',' if srt else '.'}{millis:03d}"


def validate_segments(raw: object) -> list[Segment]:
    if not isinstance(raw, list) or len(raw) > 100_000:
        raise ValueError("字幕列表格式无效或条目过多。")
    result = []
    for row in raw:
        if not isinstance(row, dict):
            raise ValueError("字幕条目格式无效。")
        start, end, text = row.get("start"), row.get("end"), row.get("text")
        if (type(start) not in (int, float) or type(end) not in (int, float)
                or not math.isfinite(start) or not math.isfinite(end)
                or start < 0 or end <= start or end > 360_000):
            raise ValueError("字幕时间无效（必须是 0–100 小时内的有效起止时间）。")
        if not isinstance(text, str) or len(text) > 100_000:
            raise ValueError("字幕文字格式无效。")
        result.append(Segment(float(start), float(end), text))
    return sorted(result, key=lambda item: (item.start, item.end))


def read_json(path: Path) -> dict:
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("项目文件超过 20 MB，无法读取。")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("文件不是有效的项目对象。")
    return data


def atomic_write(path: Path, content: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".videonotes-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path: Path, data: dict) -> None:
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))


def save_project(path: Path, project: Project) -> None:
    video = project.video
    if video:
        try:
            video = os.path.relpath(video, path.parent)
        except ValueError:
            pass  # Windows drives may differ.
    write_json(path, {"version": 1, "video": video, "notes": project.notes,
                      "segments": [asdict(item) for item in project.segments]})


def load_project(path: Path) -> Project:
    data = read_json(path)
    if data.get("version") != 1:
        raise ValueError("不支持此项目版本。")
    video, notes = data.get("video", ""), data.get("notes", "")
    if not isinstance(video, str) or not isinstance(notes, str):
        raise ValueError("视频路径或笔记格式无效。")
    if "\x00" in video:
        raise ValueError("视频路径无效。")
    if video:
        video = str((path.parent / video).resolve())
    return Project(video, validate_segments(data.get("segments", [])), notes)


def export_text(project: Project, kind: str) -> str:
    if kind == "srt":
        blocks = []
        for i, row in enumerate(project.segments, 1):
            # Blank lines terminate SRT blocks; preserve content without creating invalid blocks.
            clean = "\n".join(line for line in row.text.strip().splitlines() if line.strip()) or "…"
            blocks.append(f"{i}\n{timestamp(row.start, True)} --> {timestamp(row.end, True)}\n{clean}")
        return "\n\n".join(blocks) + ("\n" if blocks else "")
    if kind == "txt":
        text = "\n".join(row.text for row in project.segments)
        return text + ("\n\n—— 我的笔记 ——\n" + project.notes if project.notes else "") + "\n"
    if kind == "md":
        title = Path(project.video).stem if project.video else "视频"
        lines = [f"# {title} · 字幕笔记", "", "## 完整字幕", ""]
        lines.extend(f"**{timestamp(row.start)}**  \n{row.text}\n" for row in project.segments)
        if project.notes:
            lines.extend(["## 我的笔记", "", project.notes])
        return "\n".join(lines) + "\n"
    raise ValueError("不支持的导出格式。")
