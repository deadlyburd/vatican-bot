@echo off
title Vatican Agent
cd /d "%~dp0"
:loop
echo [%date% %time%] Starting Vatican Agent...
python vatican_agent.py
echo [%date% %time%] Agent stopped — restarting in 5s...
timeout /t 5 /nobreak >nul
goto loop
