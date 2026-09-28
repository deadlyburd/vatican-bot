@echo off
REM Install Vatican Sniper to the Windows Startup folder.
REM Usage: install_windows.bat "C:\path\to\dist\vatican-sniper\vatican-sniper.exe"
setlocal

set "BIN=%~1"
if "%BIN%"=="" set "BIN=%CD%\..\dist\vatican-sniper\vatican-sniper.exe"

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
powershell -NoProfile -Command "$W=New-Object -ComObject WScript.Shell; $s=$W.CreateShortcut('%STARTUP%\VaticanSniper.lnk'); $s.TargetPath='%BIN%'; $s.Arguments='--no-browser'; $s.WorkingDirectory='%~dp0'; $s.Save()"

echo Installed shortcut in Startup folder:
echo   %STARTUP%\VaticanSniper.lnk
echo Dashboard will run at http://localhost:8765 (open it in any browser).
