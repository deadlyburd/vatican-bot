#!/bin/bash

# Real Booking Test - August 13, 2026 at 17:00
# Tests the complete booking flow with extension in headful mode

set -e

echo "========================================="
echo "🎯 REAL BOOKING TEST"
echo "========================================="
echo "Date: August 13, 2026"
echo "Time: 17:00"
echo "Visitors: 1 person"
echo "Mode: Headful (visible Chrome)"
echo "========================================="
echo ""

# Check if backend is running
echo "🔍 Checking backend status..."
if ! docker-compose ps | grep -q "backend.*Up"; then
    echo "❌ Backend is not running!"
    echo "   Starting backend..."
    docker-compose up -d backend redis
    echo "   Waiting 10 seconds for backend to start..."
    sleep 10
fi
echo "✅ Backend is running"
echo ""

# Check if Chrome is already running with extension
echo "🔍 Checking Chrome status..."
if pgrep -f "google-chrome.*browser-extension" > /dev/null; then
    echo "⚠️  Chrome is already running with the extension."
    echo "   You can either:"
    echo "   1. Keep it running and just reload the extension at chrome://extensions/"
    echo "   2. Close it and this script will launch a fresh instance"
    echo ""
    read -p "Continue with existing Chrome? (y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Please close Chrome and run this script again."
        exit 1
    fi
    CHROME_RUNNING=true
else
    CHROME_RUNNING=false
fi

# Launch Chrome if not running
if [ "$CHROME_RUNNING" = false ]; then
    echo "🚀 Launching Chrome with extension (headful mode)..."
    google-chrome \
        --load-extension=/home/abiilesh/Documents/bot/bot/browser-extension \
        --disable-extensions-except=/home/abiilesh/Documents/bot/bot/browser-extension \
        --user-data-dir=/home/abiilesh/Documents/bot/bot/test_profile \
        --no-first-run \
        https://tickets.museivaticani.va/ > /dev/null 2>&1 &
    
    echo "✅ Chrome launched!"
    echo "   Waiting 5 seconds for Chrome to initialize..."
    sleep 5
fi

echo ""
echo "========================================="
echo "📋 MANUAL STEPS (Do this now):"
echo "========================================="
echo ""
echo "1. Click the Vatican Ticket Monitor extension icon"
echo "2. Configure the extension:"
echo "   - Backend URL: http://localhost:8000"
echo "   - Mode: 🚀 Backend Listener"
echo "   - Max Concurrent Bookings: 1"
echo "   - Click 'Start Monitoring'"
echo ""
echo "3. You should see: 'Backend listener started'"
echo ""
read -p "Press Enter when extension is configured and monitoring..."
echo ""

echo "========================================="
echo "🎫 Creating Test Booking Slot"
echo "========================================="
echo ""

# Create a Python script to add the slot
cat > /tmp/add_test_slot.py << 'EOF'
import os
import sys
import django

# Setup Django
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from backend.models import AvailableSlot
from datetime import datetime

# Create the slot for August 13, 2026 at 17:00
slot_data = {
    'date': '13/08/2026',
    'time': '17:00',
    'ticket_id': '2129030053',  # This will be resolved dynamically by extension
    'ticket_name': 'Musei Vaticani - Biglietti d\'ingresso',
    'visitors': 1,
    'adult_count': 1,
    'child_count': 0,
    'language': '',  # Empty for standard ticket
    'profile': {
        'first_name': 'Mario',
        'last_name': 'Rossi',
        'email': 'mario.rossi@example.com',
        'phone': '+39 123 456 7890',
        'country': 'IT'
    },
    'participants': [
        {
            'first_name': 'Mario',
            'last_name': 'Rossi',
            'email': 'mario.rossi@example.com'
        }
    ],
    'card': {
        'number': '4111111111111111',
        'expiry': '12/28',
        'cvv': '123',
        'holder': 'MARIO ROSSI'
    }
}

# Check if slot already exists
existing = AvailableSlot.objects.filter(
    date='13/08/2026',
    time='17:00',
    status='available'
).first()

if existing:
    print(f"✅ Slot already exists: {existing.id}")
    print(f"   Date: {existing.date} {existing.time}")
    print(f"   Visitors: {existing.visitors}")
else:
    # Create new slot
    slot = AvailableSlot.objects.create(
        date=slot_data['date'],
        time=slot_data['time'],
        ticket_id=slot_data['ticket_id'],
        ticket_name=slot_data['ticket_name'],
        visitors=slot_data['visitors'],
        adult_count=slot_data['adult_count'],
        child_count=slot_data['child_count'],
        language=slot_data['language'],
        profile=slot_data['profile'],
        participants=slot_data['participants'],
        card=slot_data['card'],
        status='available'
    )
    print(f"✅ Created new slot: {slot.id}")
    print(f"   Date: {slot.date} {slot.time}")
    print(f"   Visitors: {slot.visitors}")
    print(f"   Ticket: {slot.ticket_name}")

print("")
print("🎯 Slot is ready for booking!")
EOF

# Execute the Python script in the backend container
echo "📝 Adding slot to database..."
docker-compose exec -T backend python /tmp/add_test_slot.py

echo ""
echo "========================================="
echo "🚀 BOOKING FLOW STARTED"
echo "========================================="
echo ""
echo "What should happen now:"
echo ""
echo "1. Extension polls backend every 10 seconds"
echo "2. Extension finds the available slot"
echo "3. Extension opens a REGULAR window (not incognito)"
echo "4. Extension navigates to Vatican booking page"
echo "5. Extension auto-fills the booking form:"
echo "   - Date: August 13, 2026"
echo "   - Time: 17:00"
echo "   - Visitor: Mario Rossi"
echo "   - Email: mario.rossi@example.com"
echo "6. Extension proceeds through checkout"
echo "7. Extension fills payment details (test card)"
echo "8. Extension completes the booking"
echo ""
echo "========================================="
echo "👀 WATCH THE CHROME WINDOW"
echo "========================================="
echo ""
echo "You should see:"
echo "✅ A new regular window opens"
echo "✅ Vatican website loads"
echo "✅ Form fields auto-fill"
echo "✅ Booking proceeds automatically"
echo ""
echo "Press Ctrl+C to stop monitoring"
echo ""

# Monitor the backend logs
echo "📊 Backend logs (last 20 lines, updating every 5 seconds):"
echo "========================================="
while true; do
    docker-compose logs --tail=20 backend | grep -E "(available|slot|booking|vatican)" || true
    sleep 5
done
