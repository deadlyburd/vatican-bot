#!/usr/bin/env bash
# Install Vatican Sniper as a Linux user service (systemd --user).
# Usage: ./install_linux.sh "/path/to/dist/vatican-sniper/vatican-sniper"
set -euo pipefail

BIN="${1:-$PWD/../dist/vatican-sniper/vatican-sniper}"
DIR="$HOME/.config/systemd/user"

mkdir -p "$DIR"
cat > "$DIR/vatican-sniper.service" <<EOF
[Unit]
Description=Vatican Sniper
After=network.target

[Service]
ExecStart=${BIN} --no-browser
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now vatican-sniper.service
echo "Installed + started vatican-sniper.service"
echo "Dashboard at http://localhost:8765 (open it in any browser)."
