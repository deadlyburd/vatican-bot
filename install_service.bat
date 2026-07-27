@echo off
:: Run as Administrator
:: Installs Vatican Agent as a Windows Task Scheduler task (runs at login, restarts on failure)

set SCRIPT_DIR=%~dp0
set PYTHON=python
set TASK_NAME=VaticanAgent

echo Installing Vatican Agent as Windows startup task...

:: Remove existing task if present
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

:: Create task: runs at logon, restarts every 1 minute if it fails
schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%SCRIPT_DIR%run_agent.bat\"" ^
  /sc onlogon ^
  /rl highest ^
  /f

echo.
echo ✅ Task created: %TASK_NAME%
echo    Runs automatically at Windows login.
echo    To start now: schtasks /run /tn "%TASK_NAME%"
echo    To stop:      schtasks /end /tn "%TASK_NAME%"
echo    To remove:    schtasks /delete /tn "%TASK_NAME%" /f
echo.
pause
