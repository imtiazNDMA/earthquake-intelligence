@echo off
REM ---------------------------------------------------------------------
REM  Rebuild the element-layer indexes from the source GeoJSON files.
REM  Run this once after setup, and again whenever a layer changes.
REM
REM  Usage:  build_cache.bat              rebuild anything stale
REM          build_cache.bat --force      rebuild everything
REM          build_cache.bat roads        rebuild one layer
REM ---------------------------------------------------------------------
setlocal
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [ERROR] Virtual environment not found at "%PY%".
    pause
    exit /b 1
)

"%PY%" "%~dp0scripts\build_cache.py" %*

echo.
pause
endlocal
