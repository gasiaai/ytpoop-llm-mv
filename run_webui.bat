@echo off
:: Add local ffmpeg to PATH if it exists
if exist "%~dp0ffmpeg\bin\ffmpeg.exe" (
    set "PATH=%~dp0ffmpeg\bin;%PATH%"
)
echo Starting YTPoop LLM Music Video Generator — Web UI
echo Open: http://localhost:7861
echo.
python "%~dp0app.py"
pause
