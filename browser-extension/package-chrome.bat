@echo off
REM Package extension for Chrome Web Store (Windows)

echo Packaging Vatican Ticket Monitor for Chrome Web Store...

REM Create clean directory
if exist dist rmdir /s /q dist
mkdir dist
mkdir dist\vatican-monitor

REM Copy extension files
xcopy /E /I /Y browser-extension dist\vatican-monitor

REM Remove unnecessary files
cd dist\vatican-monitor
del /Q *.bat *.sh *.md 2>nul

REM Create ZIP (requires PowerShell)
cd ..
powershell Compress-Archive -Path vatican-monitor\* -DestinationPath vatican-monitor-chrome.zip -Force

echo.
echo Package created: dist\vatican-monitor-chrome.zip
echo.
echo Next steps:
echo 1. Go to https://chrome.google.com/webstore/devconsole
echo 2. Pay one-time $5 developer fee
echo 3. Upload vatican-monitor-chrome.zip
echo 4. Fill in store listing details
echo 5. Submit for review (1-3 days)

pause
