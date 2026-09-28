#!/usr/bin/env bash
# Build the macOS .app bundle for INTEL Macs (x86_64).
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

echo "[build] running PyInstaller (Intel .app)..."
APP_NAME="Vatican Sniper (Intel).app" TARGET_ARCH=x86_64 \
  "$PY" -m PyInstaller --clean --noconfirm packaging/vatican-sniper.app.spec

echo "[build] done → dist/Vatican Sniper (Intel).app"
