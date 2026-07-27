#!/bin/bash

# Complete Vatican Booking Flow - End-to-End Test
# Tests the entire flow from Bokun booking to Telegram payment link

set -e

echo "========================================="
echo "🎯 COMPLETE VATICAN BOOKING FLOW TEST"
echo "========================================="
echo ""
echo "This will test the entire flow:"
echo "1. Add booking to Google Sheets (simulates Bokun)"
echo "2. Start Vatican monitor (checks API)"
echo "3. Detect availability"
echo "4. Extension opens 3 browser windows"
echo "5. Auto-fill and hold tickets"
echo "6. Generate payment links"
echo "7. Send to Telegram"
echo ""
echo "========================================="
echo ""

# Check prerequisites
echo "🔍 Checking prerequisites..."
echo ""

# Check if backend is running
if ! docker ps | grep -q "bot_backend_1.*Up"; then
    echo "❌ Backend is not running!"
    echo "   Starting backend..."
    docker-compose up -d backend redis worker_vatican beat
    echo "   Waiting 15 seconds for services to start..."
    sleep 15
fi
echo "✅ Backend is running"

# Check if Chrome is running
if pgrep -f "google-chrome.*browser-extension" > /dev/null; then
    echo "✅ Chrome is running with extension"
    CHROME_RUNNING=true
else
    echo "⚠️  Chrome is not running"
    echo "   Launching Chrome..."
    google-chrome \
        --load-extension=/home/abiilesh/Documents/bot/bot/browser-extension \
        --disable-extensions-except=/home/abiilesh/Documents/bot/bot/browser-extension \
        --user-data-dir=/home/abiilesh/Documents/bot/bot/test_profile \
        --no-first-run \
        https://tickets.museivaticani.va/ > /dev/null 2>&1 &
    echo "   Waiting 5 seconds for Chrome to start..."
    sleep 5
    CHROME_RUNNING=false
fi

echo ""
echo "========================================="
echo "📋 STEP 1: Add Test Booking to Google Sheets"
echo "========================================="
echo ""

# Create Python script to add booking
cat > /tmp/add_test_booking.py << 'EOF'
import os
import sys
import django

sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from backend.services.bokun_sheets_sync import get_bokun_sync

print("📝 Adding test booking to Google Sheets...")

sheets = get_bokun_sync()

booking_data = {
    'booking_id': 'TEST-BOKUN-AUG13',
    'date': '13/08/2026',
    'time': '17:00',
    'visitors': 1,
    'ticket_type': 'Vatican Museums - Standard Entry',
    'customer': {
        'first_name': 'Mario',
        'last_name': 'Rossi',
        'email': 'mario.rossi@example.com',
        'phone': '+39 123 456 7890'
    },
    'participants': [
        {
            'first_name': 'Mario',
            'last_name': 'Rossi',
            'email': 'mario.rossi@example.com'
        }
    ],
    'status': 'Pending',
    'notes': 'Test booking for complete flow test'
}

try:
    sheets.add_booking_from_bokun(booking_data)
    print('✅ Test booking added to Google Sheets')
    print(f'   Booking ID: {booking_data["booking_id"]}')
    print(f'   Date: {booking_data["date"]} at {booking_data["time"]}')
    print(f'   Customer: {booking_data["customer"]["first_name"]} {booking_data["customer"]["last_name"]}')
except Exception as e:
    print(f'❌ Failed to add booking: {e}')
    sys.exit(1)
EOF

docker cp /tmp/add_test_booking.py bot_backend_1:/tmp/
docker exec bot_backend_1 python /tmp/add_test_booking.py

echo ""
echo "========================================="
echo "🔍 STEP 2: Start Vatican Monitor"
echo "========================================="
echo ""

# Create Python script to start monitor
cat > /tmp/start_monitor.py << 'EOF'
import os
import sys
import django

sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from backend.monitors.tasks import run_god_tier_vatican_monitor

print("🚀 Starting Vatican monitor for August 13, 2026...")

# Start monitor task
result = run_god_tier_vatican_monitor.delay(
    date='13/08/2026',
    ticket_id=None,  # Will be resolved dynamically
    ticket_name='Musei Vaticani - Biglietti d\'ingresso',
    language='',  # Empty for standard ticket
    task_ids=[],
    visitors=1
)

print(f'✅ Monitor task started: {result.id}')
print('   Bot will check Vatican API every 30 seconds')
print('   Waiting for availability...')
EOF

docker cp /tmp/start_monitor.py bot_backend_1:/tmp/
docker exec bot_backend_1 python /tmp/start_monitor.py

echo ""
echo "========================================="
echo "🎯 STEP 3: Configure Extension"
echo "========================================="
echo ""

if [ "$CHROME_RUNNING" = false ]; then
    echo "📋 Configure the extension now:"
    echo ""
    echo "1. Click the Vatican Ticket Monitor extension icon"
    echo "2. Set Backend URL: http://localhost:8000"
    echo "3. Set Mode: 🚀 Backend Listener"
    echo "4. Set Max Concurrent Bookings: 3"
    echo "5. Click 'Start Monitoring'"
    echo ""
    read -p "Press Enter when extension is configured and monitoring..."
else
    echo "⚠️  Make sure extension is configured:"
    echo "   - Backend URL: http://localhost:8000"
    echo "   - Mode: 🚀 Backend Listener"
    echo "   - Max Concurrent Bookings: 3"
    echo "   - Status: Monitoring"
    echo ""
    read -p "Press Enter to continue..."
fi

echo ""
echo "========================================="
echo "⚡ STEP 4: Trigger Availability (Fast Test)"
echo "========================================="
echo ""

echo "For immediate testing, we'll manually add the available slot."
echo "In production, the monitor would detect this automatically."
echo ""

# Copy and run the trigger script
docker cp /home/abiilesh/Documents/bot/bot/TRIGGER_AUGUST_13_BOOKING.py bot_backend_1:/app/
docker exec bot_backend_1 python /app/TRIGGER_AUGUST_13_BOOKING.py

echo ""
echo "========================================="
echo "👀 STEP 5: Watch the Flow!"
echo "========================================="
echo ""

echo "What should happen now (within 10-30 seconds):"
echo ""
echo "1. ✅ Extension detects available slot"
echo "2. ✅ Opens 3 browser windows"
echo "3. ✅ Auto-fills forms with Mario Rossi"
echo "4. ✅ Holds tickets (doesn't complete payment)"
echo "5. ✅ Generates payment links"
echo "6. ✅ Sends links to Telegram"
echo ""
echo "========================================="
echo ""

echo "📊 Monitoring logs (Ctrl+C to stop)..."
echo ""

# Monitor logs in real-time
docker logs -f bot_backend_1 2>&1 | grep --line-buffered -E "(vatican|slot|booking|available|held|payment|telegram)" &
LOG_PID=$!

# Wait for user to stop
echo ""
echo "Press Ctrl+C when you've seen the complete flow..."
trap "kill $LOG_PID 2>/dev/null; exit 0" INT

wait $LOG_PID
