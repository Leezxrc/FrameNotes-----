# 验证记录

验证日期：2026-10-13；环境：Windows 11 x64，Python 3.12.14。

## 已通过

- 9 项自动化测试：毫秒时间戳、非法时间拒绝、中文与相对路径项目保存恢复、写入失败保留原文件、SRT 分段与 TXT/Markdown 导出、编辑/搜索/复制/同步、取消与空结果保留旧字幕、成功结果保留笔记、失败结果保留字幕。
- 真实音视频流程：使用 Windows 本地语音合成生成 14 秒英语音轨，制作 H.264/AAC MP4；Base 模型识别出 2 条时间轴字幕，文字包含完整测试内容。
- 原生 Windows 打包程序 `dist/VideoNotes/VideoNotes.exe` 完整通过：播放器收到 41 帧，时长 14000 ms，生成 2 条字幕；完成 SRT、TXT、Markdown 导出，以及 JSON 项目保存重开。
- 打包测试清除了 PYTHONPATH/PYTHONHOME，将子进程 PATH 限制为 Windows System32，验证没有依赖系统 FFmpeg 或开发虚拟环境启动应用。
- 实际中文界面截图：`.test-artifacts/packaged-preview.png`。Qt 原生视频表面的画面不一定出现在窗口截图中，另以有效解码帧回调验证播放器。
- 便携程序目录约 354 MiB，不含语音识别模型；必须保留 EXE 同目录的 `_internal` 文件夹。

## 修复的问题

- PyAV 19 删除了 faster-whisper 1.2.1 使用的接口，已固定为 PyAV 18.1.0。参考 [上游问题说明](https://github.com/SYSTRAN/faster-whisper/issues/1589)。
- 打包工具曾从开发环境 PATH 收集到不兼容的旧系统 DLL，已在构建配置中隔离 PATH，重新构建并通过实际 EXE 测试。

## 验证边界

- 本次使用本机已有 Base 模型缓存；没有重复下载完整模型。
- 已验证清晰英语短视频，未评测中文准确率、嘈杂音轨、数小时视频或所有编解码器。
- 未在另一台全新 Windows 电脑测试，未制作安装器或进行代码签名。

## 复现

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\tools\make_fixture.ps1
.\.venv\Scripts\python.exe tools/integration.py
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean VideoNotes.spec
.\.venv\Scripts\python.exe tools/test_packaged.py
```

后两项端到端测试读取 `.test-artifacts/demo.mp4`，执行本地识别并写入该目录；打包测试会启动原生窗口并自动退出。
