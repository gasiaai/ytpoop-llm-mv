@echo off
chcp 65001 >nul 2>&1
title YTPoop LLM MV Generator — Installer
echo.
echo  ============================================
echo   YTPoop LLM Music Video Generator — Setup
echo  ============================================
echo.

:: ─── Check Python ───────────────────────────────────────────────────────────
echo [1/3] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Python not found!
    echo  Please install Python 3.10+ from https://www.python.org/downloads/
    echo  IMPORTANT: Check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do echo  Found Python %%v

:: ─── Check/Install ffmpeg ───────────────────────────────────────────────────
echo.
echo [2/3] Checking ffmpeg...

:: Check if ffmpeg is already in PATH
where ffmpeg >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=3" %%v in ('ffmpeg -version 2^>^&1 ^| findstr /i "ffmpeg version"') do echo  Found ffmpeg %%v ^(system PATH^)
    goto :pip_install
)

:: Check if we already downloaded it locally
if exist "%~dp0ffmpeg\bin\ffmpeg.exe" (
    echo  Found ffmpeg ^(local^)
    goto :pip_install
)

echo  ffmpeg not found — downloading portable version...
echo.

:: Download ffmpeg release (essentials build from gyan.dev)
set "FFMPEG_ZIP=%~dp0ffmpeg_download.zip"
set "FFMPEG_URL=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

echo  Downloading from gyan.dev ...
powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri '%FFMPEG_URL%' -OutFile '%FFMPEG_ZIP%' }"
if errorlevel 1 (
    echo.
    echo  [ERROR] Download failed!
    echo  Please download ffmpeg manually:
    echo    https://github.com/BtbN/FFmpeg-Builds/releases
    echo  Extract and put the 'bin' folder inside a 'ffmpeg' folder here.
    echo.
    pause
    exit /b 1
)

echo  Extracting...
powershell -Command "& { $ProgressPreference = 'SilentlyContinue'; Expand-Archive -Path '%FFMPEG_ZIP%' -DestinationPath '%~dp0ffmpeg_temp' -Force }"
if errorlevel 1 (
    echo  [ERROR] Extract failed!
    pause
    exit /b 1
)

:: Move extracted folder (it has a versioned name) to ffmpeg/
for /d %%d in ("%~dp0ffmpeg_temp\ffmpeg-*") do (
    if exist "%~dp0ffmpeg" rmdir /s /q "%~dp0ffmpeg"
    move "%%d" "%~dp0ffmpeg" >nul
)

:: Cleanup
rmdir /s /q "%~dp0ffmpeg_temp" 2>nul
del "%FFMPEG_ZIP%" 2>nul

if exist "%~dp0ffmpeg\bin\ffmpeg.exe" (
    echo  ffmpeg installed successfully!
) else (
    echo  [ERROR] ffmpeg extraction failed.
    echo  Please install ffmpeg manually.
    pause
    exit /b 1
)

:: ─── Install Python packages ────────────────────────────────────────────────
:pip_install
echo.
echo [3/3] Installing Python packages...
echo.
pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo.
    echo  [WARNING] Some packages may have failed to install.
    echo  If torch fails, install manually:
    echo    pip install torch --index-url https://download.pytorch.org/whl/cu121
    echo.
)

:: ─── Done ───────────────────────────────────────────────────────────────────
echo.
echo  ============================================
echo   Setup complete!
echo  ============================================
echo.
echo  To start the app, run: run_webui.bat
echo.
pause
