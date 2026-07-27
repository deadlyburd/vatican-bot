@echo off
REM Clean Extension for Deployment (Windows)
REM This script removes development files and creates a clean package

echo Cleaning extension for deployment...

REM Remove development/debug files
if exist ticketsa.museivaticani.va.har del ticketsa.museivaticani.va.har
if exist create-icons.html del create-icons.html

REM Remove all markdown documentation (keep only essential ones)
if exist AUTO_BOOKING_GUIDE.md del AUTO_BOOKING_GUIDE.md
if exist BACKEND_LISTENER_GUIDE.md del BACKEND_LISTENER_GUIDE.md
if exist BACKEND_LISTENER_MODE.md del BACKEND_LISTENER_MODE.md
if exist CHANGELOG.md del CHANGELOG.md
if exist DEBUG_FALSE_NEGATIVES.md del DEBUG_FALSE_NEGATIVES.md
if exist DEBUG_TAB_RELOAD.md del DEBUG_TAB_RELOAD.md
if exist DEEP_CHECK_MODE.md del DEEP_CHECK_MODE.md
if exist DEPLOYMENT_CHECKLIST.md del DEPLOYMENT_CHECKLIST.md
if exist EXTENSION_SUMMARY.md del EXTENSION_SUMMARY.md
if exist FIX_RELOAD_LOOP.md del FIX_RELOAD_LOOP.md
if exist MULTI_BOOKING_SOLUTION.md del MULTI_BOOKING_SOLUTION.md
if exist PACKAGE_LOCAL.md del PACKAGE_LOCAL.md
if exist QUICK_REFERENCE.md del QUICK_REFERENCE.md
if exist QUICK_VISUAL_CHECK.md del QUICK_VISUAL_CHECK.md
if exist RATE_LIMIT_GUIDE.md del RATE_LIMIT_GUIDE.md
if exist STRICT_TIME_SELECTION.md del STRICT_TIME_SELECTION.md
if exist TAB_RELOAD_MODE.md del TAB_RELOAD_MODE.md
if exist TEST_GUIDE.md del TEST_GUIDE.md
if exist TESTING_GUIDE.md del TESTING_GUIDE.md
if exist TIMING_AND_HOLD_MODE.md del TIMING_AND_HOLD_MODE.md
if exist VISUAL_CHECK_MODE.md del VISUAL_CHECK_MODE.md

echo Cleaned development files

REM Create deployment package
set PACKAGE_NAME=vatican-auto-booking-extension-v1.0.zip

echo Creating deployment package: %PACKAGE_NAME%

REM Use PowerShell to create zip (Windows 10+)
powershell -Command "Compress-Archive -Path manifest.json,background.js,content.js,popup.html,popup.js,popup.css,options.html,options.js,settings.html,settings.js,icons,README.md,INSTALLATION.md,QUICK_START.md -DestinationPath ..\%PACKAGE_NAME% -Force"

echo Package created: %PACKAGE_NAME%
echo.
echo Package contents:
echo    - Core files: manifest.json, background.js, content.js
echo    - UI files: popup.*, options.*, settings.*
echo    - Icons: icons/
echo    - Documentation: README.md, INSTALLATION.md, QUICK_START.md
echo.
echo Ready to deploy to other computers!
echo    1. Copy %PACKAGE_NAME% to target computer
echo    2. Unzip the file
echo    3. Load unpacked extension in Chrome

pause
