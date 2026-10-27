@echo off
REM ---------------------------------------------------------------------
REM  EQ-ARC exposure API - start the server and open the demo page.
REM
REM  Binds to 0.0.0.0, so the API is reachable from other machines on the
REM  network as well as from this one. To keep it local only, change HOST
REM  below to 127.0.0.1.
REM
REM  If PORT is already taken by another program, the next free port is
REM  used instead and the browser is opened on that one.
REM
REM  If other machines cannot connect, run allow_firewall.bat once as
REM  administrator to open the port.
REM ---------------------------------------------------------------------
setlocal
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
set "HOST=0.0.0.0"
set "PORT=5000"

if not exist "%PY%" (
    echo [ERROR] Virtual environment not found at "%PY%".
    echo         Create it with:  py -3.11 -m venv .venv
    echo         then install:    .venv\Scripts\python -m pip install numpy shapely flask flask-cors
    echo         and the GDAL wheel for cp311.
    pause
    exit /b 1
)

if not exist "%~dp0data\cache\population.npz" (
    echo.
    echo [!] Layer caches are missing or incomplete - building them now.
    echo     This reads ~2.4 GB of GeoJSON and only has to happen once.
    echo.
    "%PY%" "%~dp0scripts\build_cache.py"
    if errorlevel 1 (
        echo.
        echo [ERROR] Cache build failed. See the messages above.
        pause
        exit /b 1
    )
)

REM --- find a free port, starting at PORT --------------------------------
set "WANTED=%PORT%"
for /f %%p in ('powershell -NoProfile -Command "$p=%PORT%; while ((Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)) { $p++ }; $p"') do set "PORT=%%p"

if not "%PORT%"=="%WANTED%" (
    echo.
    echo [!] Port %WANTED% is already in use by another program.
    echo     Using port %PORT% instead.
)

echo.
echo  Starting EQ-ARC exposure API on port %PORT% ^(all interfaces^)
echo  Local page:  http://127.0.0.1:%PORT%/
echo  Press Ctrl+C to stop.
echo.

REM Give the server a moment to bind before the browser opens.
start "" /b cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:%PORT%/"

"%PY%" "%~dp0scripts\server.py" --host %HOST% --port %PORT% --auto-port

echo.
echo Server stopped.
pause
endlocal
