@echo off
cd /d "%~dp0"
if exist "dist\VideoNotes\VideoNotes.exe" (
    start "" "dist\VideoNotes\VideoNotes.exe"
    exit /b 0
)
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "main.py"
    exit /b 0
)
echo Please see README.md to install or build VideoNotes.
pause
