#!/usr/bin/env bash
# Build the macOS .app bundle for APPLE SILICON Macs (arm64 / M1-M4).
# Run this ON an Apple Silicon Mac. Uses `uv` if present, else python3 + pip.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=".venv/bin/python"

# 1. venv
if [ ! -x "$PY" ]; then
  echo "[build] creating venv..."
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv
  else
    python3 -m venv .venv
  fi
fi

# 2. deps + pyinstaller
if command -v uv >/dev/null 2>&1; then
  uv pip install --python "$PY" -r requirements-desktop.txt pyinstaller
else
  "$PY" -m pip install --upgrade pip >/dev/null
  "$PY" -m pip install -r requirements-desktop.txt pyinstaller
fi

# 3. arch check
ARCH="$("$PY" -c 'import platform; print(platform.machine())')"
echo "[build] venv python arch: $ARCH"
if [ "$ARCH" != "arm64" ]; then
  echo "[build] WARNING: venv is $ARCH, not arm64 — the app will not be native."
  echo "         Recreate with an arm64 Python 3.11 (uv venv .venv --python 3.11)."
fi

# 4. build
echo "[build] running PyInstaller (Apple Silicon .app)..."
APP_NAME="Vatican Sniper (Apple Silicon).app" TARGET_ARCH=arm64 \
  "$PY" -m PyInstaller --clean --noconfirm packaging/vatican-sniper.app.spec

echo "[build] done → dist/Vatican Sniper (Apple Silicon).app"
