@echo off
title Vatican Browser Agent
echo Starting Vatican Browser Agent...
echo Close this window to stop the agent.
echo.
VaticanAgent.exe --agent %COMPUTERNAME%
pause
