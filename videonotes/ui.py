from __future__ import annotations

import bisect
import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import (QAbstractTableModel, QModelIndex, QProcess, QSettings,
                           QSortFilterProxyModel, QStandardPaths, Qt, QTimer, QUrl, Signal)
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox,
                               QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QSlider, QSplitter,
                               QTableView, QVBoxLayout, QWidget)

from .core import (Project, atomic_write, export_text, load_project, read_json,
                   save_project, timestamp, validate_segments, write_json)


STYLE = """
QMainWindow, QWidget { background: #f5f6f8; color: #20313b; font-size: 14px; }
QPushButton { background: white; border: 1px solid #d7dfe4; border-radius: 7px; padding: 8px 14px; }
QPushButton:hover { background: #edf6f5; border-color: #81b8b1; }
QPushButton:disabled { color: #97a2ac; background: #eef0f3; }
QPushButton#primary { background: #087e78; color: white; border: 0; font-weight: bold; }
QPushButton#primary:disabled { background: #96bab7; }
QLineEdit, QPlainTextEdit, QComboBox, QTableView { background: white; border: 1px solid #d7dfe4; border-radius: 6px; padding: 7px; }
QTableView { gridline-color: #edf0f3; selection-background-color: #d6eeeb; selection-color: #143e3a; }
QHeaderView::section { background: #edf1f4; padding: 9px; border: 0; color: #647681; }
QLabel#muted { color: #6d7e8b; font-size: 12px; }
QLabel#heading { font-size: 20px; font-weight: bold; }
QLabel#caption { background: #192732; color: white; font-size: 18px; padding: 14px; border-radius: 4px; }
QProgressBar { border: 0; background: #e0e7eb; border-radius: 4px; height: 7px; }
QProgressBar::chunk { background: #087e78; border-radius: 4px; }
QSplitter::handle { background: #e1e6eb; }
QMenuBar, QMenu { background: white; }
"""


class TranscriptModel(QAbstractTableModel):
    edited = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.segments = []
        self.active = -1
        self.editable = True

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.segments)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 2

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.segments[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return timestamp(row.start) if index.column() == 0 else row.text
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{timestamp(row.start)} → {timestamp(row.end)}\n{row.text}"
        if role == Qt.ItemDataRole.BackgroundRole and index.row() == self.active:
            return QColor("#d5efeb")
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return ("时间 · 点击跳转", "字幕 · 双击修改")[section]
        return None

    def flags(self, index):
        flags = super().flags(index)
        if index.column() == 1 and self.editable:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or index.column() != 1 or not self.editable:
            return False
        self.segments[index.row()].text = str(value)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
        self.edited.emit()
        return True

    def replace(self, segments):
        self.beginResetModel()
        self.segments, self.active = segments, -1
        self.endResetModel()

    def highlight(self, row):
        if row == self.active:
            return
        old, self.active = self.active, row
        for item in (old, row):
            if 0 <= item < len(self.segments):
                self.dataChanged.emit(self.index(item, 0), self.index(item, 1),
                                      [Qt.ItemDataRole.BackgroundRole])


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = Project()
        self.project_path = None
        self.dirty = False
        self.starts = []
        self.job_dir = None
        self.process = None
        self.cancelled = False
        self.settings = QSettings("VideoNotes", "Desktop")
        self.resize(1280, 850)
        self.setMinimumSize(920, 650)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.8)
        self.player.setAudioOutput(self.audio)
        self.model = TranscriptModel(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterKeyColumn(1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._build_ui()
        self._build_menu()
        self.model.edited.connect(self._edited)
        self.notes.textChanged.connect(self._notes_changed)
        self.player.positionChanged.connect(self._position)
        self.player.durationChanged.connect(lambda value: self.seek.setRange(0, value))
        self.player.playbackStateChanged.connect(self._play_state)
        self.player.errorOccurred.connect(lambda *args: self.status.setText(
            "播放失败：" + self.player.errorString() + "。仍可尝试生成字幕。"))
        self.timer = QTimer(self)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self._poll)
        self._refresh()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(14)
        header = QHBoxLayout()
        title = QLabel("视频字幕笔记")
        title.setObjectName("heading")
        header.addWidget(title)
        header.addStretch()
        self.open_button = QPushButton("导入视频")
        self.open_button.clicked.connect(self.open_video)
        header.addWidget(self.open_button)
        save = QPushButton("保存项目")
        save.clicked.connect(self.save)
        header.addWidget(save)
        export = QPushButton("导出字幕 / 笔记")
        export.clicked.connect(self.export)
        header.addWidget(export)
        layout.addLayout(header)
        self.filename = QLabel("先导入一个视频，让内容变成可检索的文字。")
        self.filename.setObjectName("muted")
        self.filename.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.filename)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 12, 0)
        self.video = QVideoWidget()
        self.video.setMinimumHeight(220)
        self.player.setVideoOutput(self.video)
        left_layout.addWidget(self.video, 4)
        self.caption = QLabel("字幕会在这里随视频同步显示")
        self.caption.setObjectName("caption")
        self.caption.setTextFormat(Qt.TextFormat.PlainText)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setWordWrap(True)
        self.caption.setMinimumHeight(65)
        self.caption.setMaximumHeight(150)
        left_layout.addWidget(self.caption)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderMoved.connect(self.player.setPosition)
        left_layout.addWidget(self.seek)
        playback = QHBoxLayout()
        self.play = QPushButton("播放")
        self.play.clicked.connect(self.toggle_play)
        playback.addWidget(self.play)
        self.clock = QLabel("00:00:00 / 00:00:00")
        playback.addWidget(self.clock)
        playback.addStretch()
        speed = QComboBox()
        speed.addItems(["0.75×", "1.0×", "1.25×", "1.5×", "2.0×"])
        speed.setCurrentIndex(1)
        speed.currentTextChanged.connect(lambda text: self.player.setPlaybackRate(float(text[:-1])))
        playback.addWidget(speed)
        left_layout.addLayout(playback)
        left_layout.addWidget(QLabel("我的笔记"))
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("记录重点、想法或待办事项…\n导出 TXT / Markdown 时会一并包含这些笔记。")
        left_layout.addWidget(self.notes, 2)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 0, 0, 0)
        toolbar = QHBoxLayout()
        self.count = QLabel("全部字幕 · 0 条")
        toolbar.addWidget(self.count)
        toolbar.addStretch()
        copy = QPushButton("复制全文")
        copy.clicked.connect(self.copy_transcript)
        toolbar.addWidget(copy)
        right_layout.addLayout(toolbar)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索字幕内容…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        right_layout.addWidget(self.search)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 150)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.clicked.connect(self._jump)
        right_layout.addWidget(self.table, 1)
        self.follow = QCheckBox("播放时跟随当前字幕（滚动列表后自动暂停跟随）")
        self.follow.setChecked(True)
        self.table.verticalScrollBar().actionTriggered.connect(lambda _: self.follow.setChecked(False))
        right_layout.addWidget(self.follow)
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([600, 620])
        layout.addWidget(split, 1)
        options = QHBoxLayout()
        options.addWidget(QLabel("识别语言"))
        self.language = QComboBox()
        for label, code in [("自动检测", None), ("中文", "zh"), ("英语", "en"), ("日语", "ja"), ("韩语", "ko")]:
            self.language.addItem(label, code)
        options.addWidget(self.language)
        options.addWidget(QLabel("识别模型"))
        self.model_choice = QComboBox()
        for label, key in [("Tiny · 最快 / 约 75 MB", "tiny"), ("Base · 均衡 / 约 145 MB", "base"),
                           ("Small · 更准 / 约 465 MB", "small"), ("Medium · 更慢 / 约 1.5 GB", "medium")]:
            self.model_choice.addItem(label, key)
        self.model_choice.setCurrentIndex(1)
        options.addWidget(self.model_choice)
        options.addStretch()
        self.cancel_button = QPushButton("取消识别")
        self.cancel_button.clicked.connect(self.cancel_job)
        self.cancel_button.hide()
        options.addWidget(self.cancel_button)
        self.transcribe = QPushButton("生成字幕")
        self.transcribe.setObjectName("primary")
        self.transcribe.clicked.connect(self.start_job)
        options.addWidget(self.transcribe)
        layout.addLayout(options)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.status = QLabel("本地识别 · 视频不上传 · 首次使用所选模型需联网下载，之后可离线使用。")
        self.status.setObjectName("muted")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def _build_menu(self):
        menu = self.menuBar().addMenu("文件")
        self.open_actions = []
        for label, shortcut, callback in [("导入视频…", "Ctrl+O", self.open_video),
                                           ("打开项目…", "Ctrl+Shift+O", self.open_project),
                                           ("重新关联视频…", "", self.relink),
                                           ("保存项目", "Ctrl+S", self.save),
                                           ("项目另存为…", "Ctrl+Shift+S", lambda: self.save(True)),
                                           ("导出字幕 / 笔记…", "Ctrl+E", self.export)]:
            action = QAction(label, self)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(lambda checked=False, cb=callback: cb())
            menu.addAction(action)
            if len(self.open_actions) < 3:
                self.open_actions.append(action)
        help_menu = self.menuBar().addMenu("帮助")
        help_action = help_menu.addAction("使用说明")
        help_action.triggered.connect(self.help)

    def _refresh(self):
        title = self.project_path.name if self.project_path else "未命名项目"
        self.setWindowTitle(f"{'* ' if self.dirty else ''}{title} — 视频字幕笔记")
        self.count.setText(f"全部字幕 · {len(self.project.segments)} 条")
        self.filename.setText(self.project.video or "先导入一个视频，让内容变成可检索的文字。")
        self.filename.setToolTip(self.project.video)
        self.transcribe.setEnabled(bool(self.project.video) and self.process is None)

    def _edited(self):
        self.dirty = True
        self._refresh()
        self._position(self.player.position())

    def _notes_changed(self):
        self.project.notes = self.notes.toPlainText()
        self._edited()

    def _filter(self, text):
        self.proxy.setFilterFixedString(text)
        self.count.setText(f"全部字幕 · {len(self.project.segments)} 条" +
                           (f" / 匹配 {self.proxy.rowCount()} 条" if text else ""))

    def _position(self, value):
        if not self.seek.isSliderDown():
            self.seek.setValue(value)
        self.clock.setText(f"{timestamp(value / 1000)[:8]} / {timestamp(self.player.duration() / 1000)[:8]}")
        active = bisect.bisect_right(self.starts, value / 1000) - 1
        if active >= 0 and value / 1000 >= self.project.segments[active].end:
            active = -1
        changed = active != self.model.active
        self.model.highlight(active)
        self.caption.setText(self.project.segments[active].text if active >= 0 else
                             ("" if self.project.segments else "字幕会在这里随视频同步显示"))
        if changed and active >= 0 and self.follow.isChecked() and self.table.state() != QAbstractItemView.State.EditingState:
            index = self.proxy.mapFromSource(self.model.index(active, 0))
            if index.isValid():
                self.table.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)

    def _jump(self, index):
        source = self.proxy.mapToSource(index)
        if source.isValid():
            self.player.setPosition(round(self.project.segments[source.row()].start * 1000))

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _play_state(self, state):
        self.play.setText("暂停" if state == QMediaPlayer.PlaybackState.PlayingState else "播放")

    def _choose_video(self):
        return QFileDialog.getOpenFileName(self, "选择本地视频", self.settings.value("last_folder", ""),
            "视频 / 音频 (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.wmv *.flv *.ts *.mp3 *.wav *.m4a *.aac *.flac);;所有文件 (*)")[0]

    def _unsaved(self):
        self.table.clearFocus()  # Commit active cell editor before checking dirty state.
        self.open_button.setFocus()
        if not self.dirty:
            return True
        choice = QMessageBox.question(self, "保存修改", "当前项目有未保存的修改，要先保存吗？",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if choice == QMessageBox.StandardButton.Save:
            return self.save()
        return choice == QMessageBox.StandardButton.Discard

    def _set_project(self, project, path=None):
        self.player.stop()
        self.project, self.project_path = project, path
        self.model.replace(project.segments)
        self.starts = [row.start for row in project.segments]
        self.notes.blockSignals(True)
        self.notes.setPlainText(project.notes)
        self.notes.blockSignals(False)
        self.search.clear()
        self.player.setSource(QUrl.fromLocalFile(project.video) if project.video and Path(project.video).is_file() else QUrl())
        self.dirty = False
        self._position(0)
        self._refresh()

    def open_video(self):
        if self.process is not None:
            return
        filename = self._choose_video()
        if not filename or not self._unsaved():
            return
        self.settings.setValue("last_folder", str(Path(filename).parent))
        self._set_project(Project(video=filename))
        self.status.setText("视频已导入。选择语言与模型，然后点击「生成字幕」。")

    def open_project(self):
        if self.process is not None:
            return
        filename, _ = QFileDialog.getOpenFileName(self, "打开字幕项目", "", "字幕笔记项目 (*.vnotes.json);;JSON (*.json)")
        if not filename:
            return
        try:
            project = load_project(Path(filename))
            if not self._unsaved():
                return
            self._set_project(project, Path(filename))
            self.status.setText("项目已打开。" if not project.video or Path(project.video).is_file() else
                                "原视频不存在，文字仍可编辑。通过「文件 → 重新关联视频」选择新位置。")
        except Exception as exc:
            self.error("无法打开项目", exc)

    def relink(self):
        if self.process is not None:
            return
        filename = self._choose_video()
        if filename:
            self.player.stop()
            self.project.video = filename
            self.player.setSource(QUrl.fromLocalFile(filename))
            self._edited()

    def save(self, save_as=False):
        self.open_button.setFocus()
        path = None if save_as else self.project_path
        if path is None:
            suggestion = (Path(self.project.video).stem if self.project.video else "字幕笔记") + ".vnotes.json"
            filename, _ = QFileDialog.getSaveFileName(self, "保存项目", suggestion, "字幕笔记项目 (*.vnotes.json)")
            if not filename:
                return False
            path = Path(filename)
            if not path.name.lower().endswith(".json"):
                path = path.with_name(path.name + ".vnotes.json")
            if str(path) != filename and path.exists():
                if QMessageBox.question(self, "覆盖文件", f"{path.name} 已存在，是否覆盖？") != QMessageBox.StandardButton.Yes:
                    return False
        try:
            save_project(path, self.project)
            self.project_path, self.dirty = path, False
            self._refresh()
            self.status.setText(f"项目已保存：{path}")
            return True
        except Exception as exc:
            self.error("保存失败", exc)
            return False

    def copy_transcript(self):
        self.open_button.setFocus()
        QApplication.clipboard().setText("\n".join(row.text for row in self.project.segments))
        self.status.setText(f"已复制全部 {len(self.project.segments)} 条字幕（不受搜索过滤影响）。")

    def export(self):
        self.open_button.setFocus()
        if not self.project.segments and not self.project.notes:
            QMessageBox.information(self, "还没有内容", "请先生成字幕或填写笔记。")
            return
        choices = "SRT 字幕 (*.srt);;纯文本与笔记 (*.txt);;Markdown 笔记 (*.md)"
        suggestion = (Path(self.project.video).stem if self.project.video else "字幕笔记")
        filename, selected = QFileDialog.getSaveFileName(self, "导出全部内容", suggestion, choices)
        if not filename:
            return
        kind = "srt" if selected.startswith("SRT") else "txt" if selected.startswith("纯") else "md"
        path = Path(filename)
        if path.suffix.lower() != "." + kind:
            path = path.with_name(path.name + "." + kind)
        # Protect content if adding the selected extension changes the dialog's target.
        if str(path) != filename and path.exists():
            if QMessageBox.question(self, "覆盖文件", f"{path.name} 已存在，是否覆盖？") != QMessageBox.StandardButton.Yes:
                return
        try:
            atomic_write(path, export_text(self.project, kind))
            self.status.setText(f"已导出：{path}")
        except Exception as exc:
            self.error("导出失败", exc)

    def _busy(self, enabled):
        self.open_button.setEnabled(not enabled)
        self.language.setEnabled(not enabled)
        self.model_choice.setEnabled(not enabled)
        self.model.editable = not enabled
        for action in self.open_actions:
            action.setEnabled(not enabled)
        self.cancel_button.setVisible(enabled)
        self._refresh()

    def start_job(self):
        if self.process is not None or not self.project.video:
            return
        self.open_button.setFocus()
        if self.project.segments:
            if QMessageBox.question(self, "重新生成字幕", "识别成功后将替换当前字幕。失败或取消会保留原字幕，笔记不受影响。是否继续？") != QMessageBox.StandardButton.Yes:
                return
        try:
            self.job_dir = tempfile.TemporaryDirectory(prefix="videonotes-")
            folder = Path(self.job_dir.name)
            cache = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / "models"
            cache.mkdir(parents=True, exist_ok=True)
            write_json(folder / "request.json", {"video": self.project.video,
                "model": self.model_choice.currentData(), "language": self.language.currentData(), "cache": str(cache)})
            self.process = QProcess(self)
            args = ["--worker", str(folder)]
            if not getattr(sys, "frozen", False):
                args.insert(0, str(Path(__file__).resolve().parents[1] / "main.py"))
            self.process.setProgram(sys.executable)
            self.process.setArguments(args)
            self.process.setStandardOutputFile(str(folder / "stdout.log"))
            self.process.setStandardErrorFile(str(folder / "stderr.log"))
            self.process.finished.connect(self._finished)
            self.process.errorOccurred.connect(self._process_error)
            self.cancelled = False
            self.progress.setRange(0, 0)
            self.status.setText("正在启动本地识别…")
            self._busy(True)
            self.timer.start()
            self.process.start()
        except Exception as exc:
            self._cleanup()
            self.error("无法启动识别", exc)

    def _poll(self):
        if self.job_dir is None:
            return
        try:
            data = read_json(Path(self.job_dir.name) / "status.json")
            value = data.get("progress", -1)
            self.progress.setRange(0, 0 if value < 0 else 100)
            if value >= 0:
                self.progress.setValue(value)
            self.status.setText(data["message"])
        except (OSError, ValueError):
            pass

    def cancel_job(self):
        if self.process is not None:
            self.cancelled = True
            self.status.setText("正在取消识别…")
            self.process.kill()

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            detail = self.process.errorString()
            self._cleanup()
            self.error("无法启动识别", detail)

    def _finished(self, code, exit_status):
        if self.job_dir is None:
            return
        folder = Path(self.job_dir.name)
        error = None
        try:
            if self.cancelled:
                self.status.setText("识别已取消，原字幕与笔记已保留。")
            elif code == 0 and (folder / "result.json").is_file():
                data = read_json(folder / "result.json")
                segments = validate_segments(data["segments"])
                if segments:
                    self.project.segments = segments
                    self.model.replace(segments)
                    self.starts = [row.start for row in segments]
                    self._edited()
                    self.status.setText(f"识别完成 · {len(segments)} 条字幕 · 语言 {data.get('language', '')}。请校对后保存或导出。")
                else:
                    self.status.setText("未识别到语音，原字幕已保留。请检查音轨或选择其他语言。")
            else:
                detail = read_json(folder / "error.json")["message"] if (folder / "error.json").is_file() else f"识别进程退出，代码 {code}。"
                error = detail
        except Exception as exc:
            error = str(exc)
        finally:
            self._cleanup()
        if error:
            self.error("识别失败，原字幕已保留", str(error) + "\n\n首次下载模型需连接网络；也请确认文件含有可解码的音轨。")

    def _cleanup(self):
        self.timer.stop()
        if self.process is not None:
            self.process.deleteLater()
            self.process = None
        if self.job_dir is not None:
            try:
                self.job_dir.cleanup()
            except OSError:
                pass
            self.job_dir = None
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._busy(False)

    def error(self, title, error):
        self.status.setText(title)
        box = QMessageBox(QMessageBox.Icon.Warning, title, str(error), parent=self)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.exec()

    def help(self):
        QMessageBox.information(self, "使用说明",
            "1. 导入本地视频，选择识别语言与模型。\n"
            "2. 点击生成字幕，首次会从 Hugging Face 下载模型。\n"
            "3. 点击字幕跳转，双击文字修改；右上角复制全文。\n"
            "4. 左下角可记笔记；导出 TXT / Markdown 会包含笔记。\n"
            "5. 保存项目后可继续编辑。项目不包含视频，请保留原视频。\n\n"
            "本机 CPU 识别，大模型更慢。嘈杂音频可能识别错误，请校对。\n"
            "字幕显示在播放器下方；SRT 可供其他播放器使用，不烧录到原视频。")

    def closeEvent(self, event):
        if self.process is not None:
            if QMessageBox.question(self, "识别进行中", "关闭将取消当前识别，是否继续？") != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.cancel_job()
            if not self.process.waitForFinished(3000):
                event.ignore()
                self.status.setText("正在停止识别，请稍后关闭窗口。")
                return
        if not self._unsaved():
            event.ignore()
            return
        self.player.stop()
        event.accept()


def run():
    app = QApplication(sys.argv)
    app.setOrganizationName("VideoNotes")
    app.setApplicationName("VideoNotes")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from .diagnostics import schedule
        QTimer.singleShot(0, lambda: schedule(window, Path(sys.argv[2])))
    return app.exec()
