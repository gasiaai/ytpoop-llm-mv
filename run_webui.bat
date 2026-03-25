@echo off
cd /d "%~dp0"

:: Add local ffmpeg to PATH if it exists
if exist "%~dp0ffmpeg\bin\ffmpeg.exe" (
    set "PATH=%~dp0ffmpeg\bin;%PATH%"
)

:: Use .venv if available, otherwise system python
if exist "%~dp0.venv\Scripts\python.exe" (
    call "%~dp0.venv\Scripts\activate.bat"
    echo Using .venv Python
) else (
    echo [WARNING] .venv not found — using system Python. Run install.bat first.
)

echo.
echo Starting YTPoop LLM Music Video Generator — Web UI
echo Open: http://localhost:7861
echo.
python "%~dp0app.py"
pause
