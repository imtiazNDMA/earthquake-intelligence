@echo off
REM ============================================================
REM  SeismicWatch - Earthquake Intensity Platform
REM  One-click launcher. Double-click this file to start the app.
REM ============================================================
setlocal

REM Always run from the folder this script lives in (location-independent).
cd /d "%~dp0"

REM src-layout: make the eqmon package importable by uvicorn.
set "PYTHONPATH=src"

REM Server settings (override by passing args, e.g.  start.bat 9000 )
set "HOST=127.0.0.1"
set "PORT=%~1"
if "%PORT%"=="" set "PORT=8000"

echo(
echo ============================================================
echo   SeismicWatch - Earthquake Intensity Platform
echo ============================================================
echo   URL:  http://%HOST%:%PORT%/
echo   Stop: close this window or press Ctrl+C
echo ============================================================
echo(

REM Fail early with a friendly message if uv is not installed.
where uv >nul 2>nul
if errorlevel 1 (
    echo ERROR: 'uv' was not found on your PATH.
    echo Install it from https://docs.astral.sh/uv/ then run this again.
    echo(
    pause
    exit /b 1
)

REM Soft warning if the Vs30 grid has not been built yet (intensity needs it).
if not exist "data\Vs30.tif" (
    echo WARNING: data\Vs30.tif not found - intensity calculations will fail.
    echo Build it once with:  uv run python scripts\rasterize_vs30.py
    echo The server will still start; map basemap and catalog will work.
    echo(
)

REM Open the browser a few seconds after the server boots (non-blocking).
start "" /b powershell -NoProfile -Command "Start-Sleep -Seconds 3; Start-Process 'http://%HOST%:%PORT%/'"

REM Launch the server in the foreground so logs show here and Ctrl+C stops it.
REM 'uv run' brings the virtual environment up to date with the lockfile first.
uv run uvicorn eqmon.api:app --host %HOST% --port %PORT%

endlocal
