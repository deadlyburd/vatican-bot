#!/usr/bin/env bash
# Zip just the files needed to BUILD the app on another machine (Mac/Windows/Linux).
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="vatican-sniper-source.zip"
rm -f "$OUT"
zip -r "$OUT" \
  sniper_app.py \
  desktop_app \
  slot_finder.py \
  requirements-desktop.txt \
  config.example.json \
  CLIENT_README.md \
  WINDOWS.md \
  packaging/vatican-sniper.spec \
  packaging/vatican-sniper.app.spec \
  packaging/build_macos_arm64.sh \
  packaging/build_macos_app.sh \
  packaging/build.sh \
  packaging/build.bat \
  packaging/autostart \
  -x "*.pyc" -x "*/__pycache__/*"

echo "Created: $OUT"
echo ""
echo "Windows : unzip, then run  packaging\\build.bat"
echo "macOS   : unzip, then run  packaging/build_macos_*.sh"
echo "Linux   : unzip, then run  packaging/build.sh"
