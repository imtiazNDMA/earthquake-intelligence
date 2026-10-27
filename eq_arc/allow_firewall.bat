@echo off
REM ---------------------------------------------------------------------
REM  Open TCP port 5000 in Windows Firewall so other machines on the
REM  network can reach the EQ-ARC exposure API.
REM
REM  RIGHT-CLICK this file and choose "Run as administrator".
REM  You only need to do this once.
REM
REM  To undo it later:
REM      netsh advfirewall firewall delete rule name="EQ-ARC Exposure API"
REM ---------------------------------------------------------------------
setlocal

set "PORT=5000"
set "RULE=EQ-ARC Exposure API"

net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] This script needs administrator rights.
    echo         Right-click allow_firewall.bat and choose "Run as administrator".
    echo.
    pause
    exit /b 1
)

echo Removing any previous rule named "%RULE%" ...
netsh advfirewall firewall delete rule name="%RULE%" >nul 2>&1

echo Adding inbound rule for TCP port %PORT% ^(private networks only^) ...
netsh advfirewall firewall add rule ^
    name="%RULE%" ^
    dir=in ^
    action=allow ^
    protocol=TCP ^
    localport=%PORT% ^
    profile=private ^
    description="Allow LAN access to the EQ-ARC MMI exposure API"

if errorlevel 1 (
    echo.
    echo [ERROR] Could not add the firewall rule.
    pause
    exit /b 1
)

echo.
echo Done. Port %PORT% is open on private networks.
echo.
echo Note: the rule is limited to the "private" network profile on purpose.
echo If this machine is on a network Windows classifies as "public", either
echo change that network to private in Windows settings, or re-run this
echo script with  profile=any  in place of  profile=private.
echo.
pause
endlocal
