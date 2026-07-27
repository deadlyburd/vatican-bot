#!/bin/bash
# ============================================================================
# Chrome Bot — Display server only (nodriver launches Chrome on demand)
# ============================================================================
# Xvfb + fluxbox + VNC ready. nodriver_booker.py launches Chrome when booking.
# ============================================================================

set -e

PROFILE_ID=${PROFILE_ID:-1}
DISPLAY_NUM=$((99 + PROFILE_ID))
VNC_PORT=$((5900 + PROFILE_ID))
SCREEN_WIDTH=${SCREEN_WIDTH:-1280}
SCREEN_HEIGHT=${SCREEN_HEIGHT:-720}
SCREEN_DEPTH=${SCREEN_DEPTH:-24}

echo "========================================="
echo "🖥️  Vatican Bot — Display #$PROFILE_ID"
echo "========================================="
echo "  VNC:      :$VNC_PORT"
echo "  Display:  :$DISPLAY_NUM"
echo "========================================="

# Clean stale locks
rm -f /tmp/.X${DISPLAY_NUM}-lock 2>/dev/null || true

# Xvfb
echo "📺 Starting Xvfb on :${DISPLAY_NUM}..."
Xvfb :${DISPLAY_NUM} \
    -screen 0 ${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH} \
    -ac +extension GLX +render -noreset &
XVFB_PID=$!
sleep 2

if ! kill -0 $XVFB_PID 2>/dev/null; then
    echo "❌ Xvfb failed"
    exit 1
fi
echo "✅ Xvfb (PID: $XVFB_PID)"
export DISPLAY=:${DISPLAY_NUM}

# Window manager
echo "🪟 Starting fluxbox..."
fluxbox &>/dev/null &
sleep 1

# VNC
echo "🔍 Starting VNC on :${VNC_PORT}..."
x11vnc -display :${DISPLAY_NUM} -forever -shared -rfbport ${VNC_PORT} -nopw &>/dev/null &
echo "✅ VNC ready on port ${VNC_PORT}"

echo ""
echo "🟢 Display #${PROFILE_ID} ready — waiting for booking commands"
echo "   VNC: :${VNC_PORT}"
echo "   Run: docker exec vatican-bot-chrome_bot_1-1 python3 /root/nodriver_booker.py --date DD/MM/YYYY"

# Keep alive
cleanup() {
    echo "🛑 Shutting down display #${PROFILE_ID}..."
    kill $XVFB_PID 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

while true; do
    sleep 60
done
