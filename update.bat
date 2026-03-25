@echo off
chcp 65001 >nul 2>&1
title YTPoop LLM MV Generator — Update
echo.
echo  ============================================
echo   YTPoop LLM Music Video Generator — Update
echo  ============================================
echo.

:: Check git
where git >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] git not found!
    echo  Please install Git from https://git-scm.com/downloads
    echo.
    pause
    exit /b 1
)

cd /d "%~dp0"

:: Save current branch
for /f "tokens=*" %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "BRANCH=%%b"
if "%BRANCH%"=="" set "BRANCH=master"

:: Stash any local changes (presets, etc.)
echo [1/3] Saving local changes...
git stash >nul 2>&1

:: Pull latest
echo [2/3] Pulling latest from origin/%BRANCH%...
git pull origin %BRANCH%
if errorlevel 1 (
    echo.
    echo  [ERROR] Update failed!
    echo  Try running: git pull origin %BRANCH% --rebase
    echo.
    git stash pop >nul 2>&1
    pause
    exit /b 1
)

:: Restore local changes
git stash pop >nul 2>&1

:: Update Python packages in .venv
echo [3/3] Updating Python packages...
if exist "%~dp0.venv\Scripts\activate.bat" (
    call "%~dp0.venv\Scripts\activate.bat"
    pip install -r "%~dp0requirements.txt" --quiet
) else (
    echo  [WARNING] .venv not found — run install.bat first.
    pip install -r "%~dp0requirements.txt" --quiet
)

if errorlevel 1 (
    echo  [WARNING] Some packages may have failed. Try running install.bat again.
)

echo.
echo  ============================================
echo   Update complete!
echo  ============================================
echo.
echo  To start the app, run: run_webui.bat
echo.
pause
