#!/bin/bash
# ============================================================================
# Chrome Bot — Starts Chrome with Vatican Auto-Booker extension
# ============================================================================
# Chrome opens with the extension which polls backend for booking commands.
# VNC available for visual monitoring.
# ============================================================================

set -e

PROFILE_ID=${PROFILE_ID:-1}
BACKEND_URL=${BACKEND_URL:-http://backend:8000}
DISPLAY_NUM=$((99 + PROFILE_ID))
VNC_PORT=$((5900 + PROFILE_ID))
DEBUG_PORT=$((9221 + PROFILE_ID))
VNC_ENABLED=${VNC_ENABLED:-false}
SCREEN_WIDTH=${SCREEN_WIDTH:-1280}
SCREEN_HEIGHT=${SCREEN_HEIGHT:-720}
SCREEN_DEPTH=${SCREEN_DEPTH:-24}

echo "========================================="
echo "🚀 Vatican Bot — Chrome #$PROFILE_ID"
echo "========================================="
echo "  VNC:      :$VNC_PORT"
echo "  Debug:    :$DEBUG_PORT"
echo "  Backend:  $BACKEND_URL"
echo "========================================="

# ── Profile & Extension Config ──────────────────────────────────────
PROFILE_DIR="/root/chrome-profiles/profile-${PROFILE_ID}"
mkdir -p "$PROFILE_DIR"

# Write extension config so it knows the backend URL
echo "📝 Writing extension config..."
cat > /root/browser-extension/config.json << EOF
{
  "autoStart": true,
  "backendUrl": "${BACKEND_URL}",
  "apiKey": "",
  "maxConcurrentBookings": 3,
  "mode": "extension_booker"
}
EOF
echo "✅ Extension config: backendUrl=${BACKEND_URL}"

# ── Clean stale locks ───────────────────────────────────────────────
rm -f /tmp/.X${DISPLAY_NUM}-lock 2>/dev/null || true
rm -f "$PROFILE_DIR/SingletonLock" "$PROFILE_DIR/SingletonCookie" "$PROFILE_DIR/SingletonSocket" 2>/dev/null || true

# ── Xvfb ────────────────────────────────────────────────────────────
echo "📺 Starting Xvfb on :${DISPLAY_NUM}..."
Xvfb :${DISPLAY_NUM} \
    -screen 0 ${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH} \
    -ac +extension GLX +render -noreset &
XVFB_PID=$!
sleep 2

if ! kill -0 $XVFB_PID 2>/dev/null; then
    echo "❌ Xvfb failed to start"
    exit 1
fi
echo "✅ Xvfb running (PID: $XVFB_PID)"
export DISPLAY=:${DISPLAY_NUM}

# ── Window Manager ──────────────────────────────────────────────────
echo "🪟 Starting fluxbox..."
fluxbox &>/dev/null &
sleep 1

# ── VNC ─────────────────────────────────────────────────────────────
if [ "$VNC_ENABLED" = "true" ]; then
    echo "🔍 Starting VNC on :${VNC_PORT}..."
    x11vnc -display :${DISPLAY_NUM} -forever -shared -rfbport ${VNC_PORT} -nopw &>/dev/null &
    echo "✅ VNC ready on port ${VNC_PORT}"
fi

# ── Chrome ──────────────────────────────────────────────────────────
echo "🌐 Starting Chrome..."

google-chrome \
    --user-data-dir="$PROFILE_DIR" \
    --load-extension=/root/browser-extension \
    --no-sandbox \
    --disable-dev-shm-usage \
    --disable-gpu \
    --disable-software-rasterizer \
    --remote-debugging-address=0.0.0.0 \
    --remote-debugging-port=$DEBUG_PORT \
    --window-size=$SCREEN_WIDTH,$SCREEN_HEIGHT \
    --start-maximized \
    --no-first-run \
    --no-default-browser-check \
    --disable-features=TranslateUI,ProfilePicker \
    --password-store=basic \
    --use-mock-keychain \
    "https://tickets.museivaticani.va/" &>/root/logs/chrome-profile-${PROFILE_ID}.log &

CHROME_PID=$!
echo "✅ Chrome running (PID: $CHROME_PID)"

# ── Keepalive ───────────────────────────────────────────────────────
# Restart Chrome if it dies, max once every 30 min
cleanup() {
    echo ""
    echo "🛑 Shutting down Chrome #${PROFILE_ID}..."
    kill $CHROME_PID 2>/dev/null || true
    [ ! -z "$VNC_PID" ] && kill $VNC_PID 2>/dev/null || true
    kill $XVFB_PID 2>/dev/null || true
    echo "✅ Cleanup complete"
    exit 0
}
trap cleanup SIGTERM SIGINT SIGQUIT

echo "🟢 Chrome #${PROFILE_ID} running — extension polling ${BACKEND_URL}"
echo "   VNC: :${VNC_PORT} | Debug: :${DEBUG_PORT}"

# Wait for Chrome and restart if it crashes
while true; do
    wait $CHROME_PID 2>/dev/null || true
    echo "⚠️ Chrome died — restarting in 5s..."
    sleep 5

    rm -f "$PROFILE_DIR/SingletonLock" "$PROFILE_DIR/SingletonCookie" "$PROFILE_DIR/SingletonSocket" 2>/dev/null || true

    google-chrome \
        --user-data-dir="$PROFILE_DIR" \
        --load-extension=/root/browser-extension \
        --no-sandbox \
        --disable-dev-shm-usage \
        --disable-gpu \
        --remote-debugging-address=0.0.0.0 \
        --remote-debugging-port=$DEBUG_PORT \
        --window-size=$SCREEN_WIDTH,$SCREEN_HEIGHT \
        --start-maximized \
        --no-first-run \
        --no-default-browser-check \
        --disable-features=TranslateUI,ProfilePicker \
        --password-store=basic \
        --use-mock-keychain \
        "https://tickets.museivaticani.va/" &>/root/logs/chrome-profile-${PROFILE_ID}.log &

    CHROME_PID=$!
    echo "✅ Chrome restarted (PID: $CHROME_PID)"
done
