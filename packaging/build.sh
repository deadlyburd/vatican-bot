#!/usr/bin/env bash
# Build the Vatican Sniper desktop app (macOS / Linux, onedir build).
# Uses `uv` if present, else python3 + pip.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=".venv/bin/python"

if [ ! -x "$PY" ]; then
  echo "[build] creating venv..."
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv
  else
    python3 -m venv .venv
  fi
fi

if command -v uv >/dev/null 2>&1; then
  uv pip install --python "$PY" -r requirements-desktop.txt pyinstaller
else
  "$PY" -m pip install --upgrade pip >/dev/null
  "$PY" -m pip install -r requirements-desktop.txt pyinstaller
fi

echo "[build] running PyInstaller (onedir)..."
"$PY" -m PyInstaller --clean --noconfirm packaging/vatican-sniper.spec

echo "[build] done → dist/vatican-sniper/"
