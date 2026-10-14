# 视频字幕笔记 · Windows 桌面版

读取本地视频，使用本机 CPU 自动生成字幕；视频在左侧播放，完整字幕显示在右侧，下方可以自由记笔记。

## 使用

双击根目录的 **启动软件.cmd**，或打开 **dist/VideoNotes/VideoNotes.exe**。

1. 点击「导入视频」，选择 MP4、MKV、MOV 等视频（也可选常见音频）。
2. 选择语言；中英文混合可先用自动检测。默认 Base 模型，Small 通常更准确，但更慢。
3. 点击「生成字幕」。首次使用所选模型需联网下载；如果用户本机已有兼容缓存，会自动复用。视频不会上传。
4. 点击字幕跳到相应位置，双击文字进行修改。搜索只过滤显示，「复制全文」和导出仍包含全部字幕。
5. 在「我的笔记」中记录重点，选择导出格式：SRT 为带时间轴的字幕；TXT 为全部文字及笔记；Markdown 为带时间点的字幕与笔记。
6. 「保存项目」保存为 `.vnotes.json`，下次用「文件 → 打开项目」继续编辑。项目不嵌入视频，请保留原视频；移动后可「重新关联视频」。

识别过程中可以播放视频、记笔记、取消任务。取消、失败、没有语音时保留现有字幕；完整成功才替换原字幕。关闭或切换项目时会提醒保存修改。

## 运行要求与说明

- Windows 10/11 64 位。Base 推荐至少 8 GB 内存；较大的模型及长视频需要更多内存。
- 无需单独安装 Python 或 FFmpeg 即可运行打包目录。分发时复制整个 `dist/VideoNotes` 文件夹，不要只复制 EXE。
- 模型约 Tiny 75 MB / Base 145 MB / Small 465 MB / Medium 1.5 GB，实际下载大小可能变化。首次下载来源为 Hugging Face，网络不可达时会提示失败，可稍后重试。
- 新下载模型位于 `%LOCALAPPDATA%\VideoNotes\VideoNotes\models`（由 Qt 用户应用数据路径决定）；也会复用标准 Hugging Face 缓存。
- CPU 转写不保证实时。噪声、音乐、口音会影响准确率；请人工校对重要内容。当前不提供翻译或说话人分离。
- 同步字幕显示在播放器下方，不修改或烧录原视频。重叠字幕优先显示开始时间较晚的一条。
- 播放与语音识别使用不同解码器，个别文件可能能识别但无法播放；可尝试转成标准 H.264/AAC MP4。
- 字幕列表自动换行，悬停可查看完整文本，双击可编辑；导出始终包含全部文字。
- 文字修改后需要保存项目；当前不提供崩溃恢复。项目读取上限 20 MB / 10 万条字幕 / 100 小时时间轴。

## 从源码运行

需要 Python 3.12（Windows x64）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

测试与构建：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm VideoNotes.spec
```

项目包含数据校验、原子保存、导出、字幕编辑/搜索/同步、识别失败与取消保留数据的测试。实际识别和打包运行验证另记录于 `VALIDATION.md`。

## 技术与第三方组件

界面和播放使用 [Qt for Python / PySide6](https://doc.qt.io/qtforpython-6/PySide6/QtMultimedia/QMediaPlayer.html)，本地识别使用 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)。模型、第三方依赖和运行库仍按各自许可证使用；公开分发前应一并核对、保留相应许可证。
