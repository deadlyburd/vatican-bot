#!/usr/bin/env bash
# Install Vatican Sniper as a macOS login item (launchd).
# Usage: ./install_macos.sh "/path/to/dist/vatican-sniper/vatican-sniper"
set -euo pipefail

BIN="${1:-$PWD/../dist/vatican-sniper/vatican-sniper}"
PLIST="$HOME/Library/LaunchAgents/com.vatican.sniper.plist"

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.vatican.sniper</string>
  <key>ProgramArguments</key>
  <array>
    <string>${BIN}</string>
    <string>--no-browser</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Installed autostart: $PLIST"
echo "Dashboard will run at http://localhost:8765 (open it in any browser)."
