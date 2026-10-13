@echo off
setlocal
cd /d "%~dp0"
where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pythonw.exe "%~dp0app.py"
    exit /b 0
)
where py.exe >nul 2>nul
if not errorlevel 1 (
    start "" py.exe -3 "%~dp0app.py"
    exit /b 0
)
echo Python 3 with Tkinter is required. Please install Python from python.org.
pause
