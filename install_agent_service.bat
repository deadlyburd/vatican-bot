@echo off
title Install Vatican Agent — Auto-start on Login
echo.
echo Installing Vatican Browser Agent to auto-start on login...
echo.

set SCRIPT_DIR=%~dp0
set VBS_PATH=%SCRIPT_DIR%start_agent_hidden.vbs
set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup

REM Copy VBS to startup folder (runs silently on login, no console window)
copy "%VBS_PATH%" "%STARTUP_DIR%\VaticanAgent.vbs" /Y

if %errorlevel% == 0 (
    echo SUCCESS! Agent will auto-start silently on next login.
    echo.
    echo To start it NOW without restarting:
    wscript "%STARTUP_DIR%\VaticanAgent.vbs"
    echo Agent started in background.
    echo.
    echo To stop it:
    echo   taskkill /f /im python.exe /fi "WINDOWTITLE eq Vatican*"
    echo.
    echo To uninstall auto-start:
    echo   del "%STARTUP_DIR%\VaticanAgent.vbs"
) else (
    echo Failed. Try running as Administrator.
)
echo.
pause
