from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata
import os

# Do not accidentally bundle unrelated runtime DLLs from developer-tool PATHs.
# Windows supplies ICU and Universal CRT; Qt/PyAV ship their own media libraries.
os.environ['PATH'] = os.path.join(os.environ['SystemRoot'], 'System32')

datas = collect_data_files('faster_whisper') + copy_metadata('faster-whisper')
binaries = collect_dynamic_libs('ctranslate2')
a = Analysis(['main.py'], pathex=[], binaries=binaries, datas=datas,
             hiddenimports=['faster_whisper', 'onnxruntime'],
             excludes=['torch', 'tensorflow', 'matplotlib', 'PySide6.QtWebEngineCore',
                       'PySide6.QtWebEngineWidgets', 'PySide6.QtQml'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='VideoNotes',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='VideoNotes')
