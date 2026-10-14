import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
environment = os.environ.copy()
environment.pop("PYTHONPATH", None)
environment.pop("PYTHONHOME", None)
environment.pop("QT_QPA_PLATFORM", None)
environment["PATH"] = os.path.join(environment["SYSTEMROOT"], "System32")
startup = subprocess.STARTUPINFO()
startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow = subprocess.SW_HIDE
process = subprocess.run([str(root / "dist" / "VideoNotes" / "VideoNotes.exe"),
    "--self-test", str(root / ".test-artifacts")], cwd=root / "dist" / "VideoNotes",
    env=environment, startupinfo=startup, timeout=150)
report = json.loads((root / ".test-artifacts" / "packaged-report.json").read_text(encoding="utf-8"))
print(json.dumps(report, ensure_ascii=True, indent=2))
assert process.returncode == 0 and report["ok"], report
