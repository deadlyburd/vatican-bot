@echo off
REM Build the Vatican Sniper desktop app (Windows, onedir).
REM Uses `uv` if present, else `python` + pip.
cd /d "%~dp0\.."

set "PY=.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo [build] creating venv...
  where uv >nul 2>nul
  if errorlevel 1 ( python -m venv .venv ) else ( uv venv .venv )
)

echo [build] installing deps + PyInstaller...
where uv >nul 2>nul
if errorlevel 1 (
  "%PY%" -m pip install --upgrade pip
  "%PY%" -m pip install -r requirements-desktop.txt pyinstaller
) else (
  uv pip install --python "%PY%" -r requirements-desktop.txt pyinstaller
)

echo [build] running PyInstaller (onedir)...
"%PY%" -m PyInstaller --clean --noconfirm packaging\vatican-sniper.spec

echo.
echo [build] done - dist\vatican-sniper\
echo         Run: dist\vatican-sniper\vatican-sniper.exe
