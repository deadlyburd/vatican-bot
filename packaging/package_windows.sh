#!/usr/bin/env bash
# Assemble a ready-to-send Windows package: source + docs + credentials.
set -euo pipefail
cd "$(dirname "$0")/.."

STAGE="$(mktemp -d)"
PKG="$STAGE/windows-sniper"
mkdir -p "$PKG"

# source
cp -R sniper_app.py slot_finder.py requirements-desktop.txt config.example.json desktop_app "$PKG/"
# packaging (Windows only)
mkdir -p "$PKG/packaging/autostart"
cp packaging/vatican-sniper.spec packaging/build.bat "$PKG/packaging/"
cp packaging/autostart/install_windows.bat "$PKG/packaging/autostart/"
# docs + credentials
cp WINDOWS.md CLIENT_README.md "$PKG/"
[ -f google_credentials.json ] && cp google_credentials.json "$PKG/" || echo "WARNING: google_credentials.json not found"

# strip caches
find "$PKG" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$PKG" -name "*.pyc" -delete 2>/dev/null || true

# READ-ME-FIRST
cat > "$PKG/READ-ME-FIRST.txt" <<'EOF'
VATICAN SNIPER — WINDOWS PACKAGE
================================

This folder has everything needed to build and run the app on Windows.

TO BUILD the .exe (one time, on any Windows PC):
  1. Install Python 3.11+ from python.org  (tick "Add python.exe to PATH")
  2. Run:   packaging\build.bat
  3. Output: dist\vatican-sniper\vatican-sniper.exe

TO RUN (the client):
  1. Double-click  dist\vatican-sniper\vatican-sniper.exe
     (SmartScreen: click "More info" -> "Run anyway")
  2. Dashboard opens at http://localhost:8765
  3. First-run: Settings -> path to google_credentials.json -> Save
                Sheets -> paste sheet URL -> Connect -> Add sheet -> Save
  4. Start to begin booking.

IMPORTANT:
  - The Google Sheet must be SHARED (Editor) with:
        pointours@hydrasnipe.iam.gserviceaccount.com
  - The PC needs Brave, Chrome, or Edge installed.
  - Must be on a residential connection (NOT a VPN / datacenter).

Full guide:   WINDOWS.md
Client guide: CLIENT_README.md
EOF

OUT="$(pwd)/windows-sniper.zip"
rm -f "$OUT"
( cd "$STAGE" && zip -r "$OUT" "windows-sniper" ) >/dev/null
rm -rf "$STAGE"

echo "Created: $OUT"
echo "Contents:"
unzip -l "$OUT" | grep -vE "^\s*$|Archive:|----" | tail -n +2 | head -40
