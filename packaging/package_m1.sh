#!/usr/bin/env bash
# Assemble a ready-to-install package for the client's M1 Mac.
# (Uses the Intel .app which runs on M1 via Rosetta 2; see READ-ME-FIRST.)
set -euo pipefail
cd "$(dirname "$0")/.."

APP="dist/Vatican Sniper (Intel).app"
[ -d "$APP" ] || { echo "Missing $APP — build it first (packaging/build_macos_app.sh)"; exit 1; }

STAGE="$(mktemp -d)"
PKG="$STAGE/Vatican-Sniper-M1"
mkdir -p "$PKG"

# app
ditto "$APP" "$PKG/Vatican Sniper.app"
# credentials + docs
[ -f google_credentials.json ] && cp google_credentials.json "$PKG/" || echo "WARNING: google_credentials.json not found"
cp CLIENT_README.md "$PKG/" 2>/dev/null || true

# READ-ME-FIRST
cat > "$PKG/READ-ME-FIRST.txt" <<'EOF'
VATICAN SNIPER — M1 (Apple Silicon) INSTALL
===========================================

What's in this folder:
  - "Vatican Sniper.app"       → the app
  - "google_credentials.json"  → the sheet-access key
  - "CLIENT_README.md"         → full instructions

INSTALL (3 steps):

1) Put the credentials in place:
   Open Finder → press Cmd+Shift+G → paste:  ~/.vatican-sniper
   (create the folder if it doesn't exist) → drop "google_credentials.json" in it.

2) Open the app:
   Right-click "Vatican Sniper.app" → Open → Open  (first time only).
   If macOS asks to install "Rosetta", click Install — one time, ~30s.

3) In the dashboard (http://localhost:8765):
   - Settings → leave credentials as "google_credentials.json" → Save
   - Manual tab → pick a date + time → Watch this slot
   - (or Sheets tab → paste your sheet URL → Connect)

NOTE: This is the Intel build, which runs on Apple Silicon via Rosetta 2
(the booking itself still uses your native Brave/Chrome, so it's just as fast).
For a native Apple Silicon build, run  packaging/build_macos_arm64.sh  on an
M-series Mac.
EOF

OUT="$(pwd)/vatican-sniper-m1.zip"
rm -f "$OUT"
( cd "$STAGE" && zip -r "$OUT" "Vatican-Sniper-M1" ) >/dev/null
rm -rf "$STAGE"

echo "Created: $OUT"
echo "Size: $(du -h "$OUT" | cut -f1)"
echo "Contents:"
unzip -l "$OUT" | grep -vE "^\s*$|Archive:|----" | head -8
