@echo off
cd /d "%~dp0"
echo Starting ePubTsuyaku Web UI...
echo Open http://127.0.0.1:7860 in your browser.
echo Closing this window stops the server.
echo.
uv run --python .venv\Scripts\python.exe webui.py
if errorlevel 1 (
  echo.
  echo Failed to start. Check dependencies and Python environment.
  pause
)