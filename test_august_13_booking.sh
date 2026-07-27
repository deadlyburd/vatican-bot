#!/bin/bash
# Test August 13th Booking Flow
# This script creates test data in Docker and launches Chrome locally

set -e

echo "================================================================================"
echo "🧪 AUGUST 13TH BOOKING FLOW TEST"
echo "================================================================================"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if Docker services are running
echo -e "\n${BLUE}📦 Checking Docker services...${NC}"
if ! docker-compose ps | grep -q "Up"; then
    echo -e "${YELLOW}⚠️  Docker services not running. Starting them...${NC}"
    docker-compose up -d
    echo -e "${GREEN}✅ Waiting for services to start...${NC}"
    sleep 10
fi

# Create test data in Docker
echo -e "\n${BLUE}📝 Creating test data for August 13, 2026 at 17:00...${NC}"
docker-compose exec -T backend python << 'PYTHON_SCRIPT'
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import Agency, MonitorTask, HeldSlot, BuyerProfile
from django.utils import timezone
import json

# Create or get test agency
agency, created = Agency.objects.get_or_create(
    name="Test Agency - August 13",
    defaults={
        'api_key': 'test-key-123',
        'plan': 'pro',
        'is_active': True,
        'telegram_chat_id': '123456789'
    }
)
print(f"✅ Agency: {agency.name} (ID: {agency.id})")

# Create buyer profile
profile, _ = BuyerProfile.objects.get_or_create(
    agency=agency,
    defaults={
        'first_name': 'Final',
        'last_name': 'Tester',
        'email': 'final.tester@example.com',
        'phone': '+39 123456789',
        'country': 'Italia',
        'city': 'Roma',
        'birth_date': '1990-01-15',
        'gender': 'M',
        'language': 'en',
        'participants_json': json.dumps([
            {
                'first_name': 'Final',
                'last_name': 'Tester',
                'email': 'final.tester@example.com',
                'phone': '+39 123456789',
                'birth_date': '1990-01-15'
            },
            {
                'first_name': 'Jane',
                'last_name': 'Doe',
                'email': 'jane.doe@example.com',
                'phone': '+39 987654321',
                'birth_date': '1992-03-20'
            }
        ])
    }
)
print(f"✅ Profile: {profile.first_name} {profile.last_name}")

# Create task
task, _ = MonitorTask.objects.get_or_create(
    agency=agency,
    site='vatican',
    dates=['2026-08-13'],
    defaults={
        'area_name': 'Vatican Museums',
        'preferred_times': ['17:00'],
        'visitors': 2,
        'adult_count': 2,
        'child_count': 0,
        'ticket_type': 0,
        'ticket_name': 'Vatican Museums - Standard Entry',
        'ticket_id': None,
        'language': None,
        'check_interval': 60,
        'tier': 'snipe',
        'match_strategy': 'any',
        'notification_mode': 'available_only',
        'is_active': True
    }
)
print(f"✅ Task: August 13, 2026 (ID: {task.id})")

# Create or update held slot
slot, created = HeldSlot.objects.get_or_create(
    task=task,
    date='13/08/2026',
    slot_time='17:00',
    defaults={
        'slot_id': 'FINAL-TEST-SLOT',
        'ticket_id': '2129030053',
        'ticket_name': 'Vatican Museums - Standard Entry',
        'visitors': 2,
        'adult_count': 2,
        'child_count': 0,
        'total_price': 34.00,
        'jsessionid': 'TEST_SESSION_FINAL',
        'ticketmv': 'TEST_TICKET_FINAL',
        'recap_id': '2026/8000/1',
        'status': 'held',
        'hold_started_at': timezone.now(),
        'last_keepalive_at': timezone.now(),
        'payment_ready': False,
        'profile_data': json.dumps({
            'first_name': profile.first_name,
            'last_name': profile.last_name,
            'email': profile.email,
            'phone': profile.phone,
            'country': profile.country,
            'city': profile.city,
            'birth_date': profile.birth_date,
            'gender': profile.gender,
            'language': profile.language
        }),
        'participants_data': profile.participants_json,
        'notes': json.dumps({
            'test': True,
            'created_by': 'test_august_13_booking',
            'serverid': 'LOCAL_TEST'
        })
    }
)

if not created:
    # Update existing slot
    slot.status = 'held'
    slot.hold_started_at = timezone.now()
    slot.last_keepalive_at = timezone.now()
    slot.payment_ready = False
    slot.save()

print(f"✅ Slot: 13/08/2026 17:00 (ID: {slot.id})")
print(f"\n📊 SUMMARY:")
print(f"   Agency ID: {agency.id}")
print(f"   Task ID: {task.id}")
print(f"   Slot ID: {slot.id}")
print(f"   Date: August 13, 2026 at 17:00")
print(f"   Visitors: 2 (Final Tester, Jane Doe)")

# Save agency ID for later use
with open('/tmp/test_agency_id.txt', 'w') as f:
    f.write(str(agency.id))
PYTHON_SCRIPT

# Get agency ID
AGENCY_ID=$(docker-compose exec -T backend cat /tmp/test_agency_id.txt)

echo -e "\n${GREEN}✅ Test data created successfully!${NC}"
echo -e "   Agency ID: ${AGENCY_ID}"

# Launch Chrome with extension
echo -e "\n${BLUE}🚀 Launching Chrome with extension...${NC}"

EXTENSION_PATH="$(pwd)/browser-extension"
PROFILE_PATH="$(pwd)/test_profile"

# Create profile directory
mkdir -p "$PROFILE_PATH"

# Launch Chrome
google-chrome \
    --load-extension="$EXTENSION_PATH" \
    --disable-extensions-except="$EXTENSION_PATH" \
    --allow-extension-incognito \
    --user-data-dir="$PROFILE_PATH" \
    --no-first-run \
    --no-default-browser-check \
    "https://tickets.museivaticani.va/" \
    > /dev/null 2>&1 &

CHROME_PID=$!

echo -e "${GREEN}✅ Chrome launched (PID: $CHROME_PID)${NC}"

# Print instructions
echo -e "\n================================================================================"
echo -e "${YELLOW}📋 TESTING INSTRUCTIONS${NC}"
echo -e "================================================================================"

echo -e "\n${BLUE}🔧 STEP 1: Enable Extension in Incognito Mode${NC}"
echo -e "────────────────────────────────────────────────────────────────────────────────"
echo -e "Chrome has opened, but you need to enable the extension for incognito mode:"
echo -e ""
echo -e "1. In Chrome, go to: ${YELLOW}chrome://extensions/${NC}"
echo -e "2. Find '${YELLOW}Vatican Ticket Monitor & Auto-Booker${NC}'"
echo -e "3. Click '${YELLOW}Details${NC}' button"
echo -e "4. Scroll down and toggle ${GREEN}ON${NC}: '${YELLOW}Allow in incognito${NC}'"
echo -e "5. You should see a checkmark ✓ next to 'Allow in incognito'"
echo -e ""
echo -e "${RED}⚠️  THIS IS CRITICAL - Without this, the extension won't work in booking windows!${NC}"

echo -e "\n${BLUE}🔧 STEP 2: Configure the Extension${NC}"
echo -e "────────────────────────────────────────────────────────────────────────────────"
echo -e "1. Click the extension icon (puzzle piece 🧩) in Chrome toolbar"
echo -e "2. Click on '${YELLOW}Vatican Ticket Monitor & Auto-Booker${NC}'"
echo -e "3. In the popup, configure:"
echo -e "   • Backend URL: ${YELLOW}http://localhost:8000${NC}"
echo -e "   • Agency ID: ${YELLOW}${AGENCY_ID}${NC}"
echo -e "   • Mode: ${YELLOW}🚀 Backend Listener${NC}"
echo -e "4. Click '${GREEN}Start Monitoring${NC}'"

echo -e "\n${BLUE}🔧 STEP 3: Watch the Magic Happen${NC}"
echo -e "────────────────────────────────────────────────────────────────────────────────"
echo -e "The extension will:"
echo -e "1. Poll the backend API every 10 seconds"
echo -e "2. Detect the available slot: ${GREEN}August 13, 2026 at 17:00${NC}"
echo -e "3. Open an ${YELLOW}INCOGNITO${NC} window automatically"
echo -e "4. Navigate to the Vatican booking page"
echo -e "5. Auto-fill the form with:"
echo -e "   • Visitor 1: ${GREEN}Final Tester${NC}"
echo -e "   • Visitor 2: ${GREEN}Jane Doe${NC}"
echo -e "6. Complete the booking flow"

echo -e "\n${BLUE}📊 VERIFICATION${NC}"
echo -e "────────────────────────────────────────────────────────────────────────────────"
echo -e "You should see:"
echo -e "✅ Extension icon shows 'Monitoring...'"
echo -e "✅ Incognito window opens within 10 seconds"
echo -e "✅ Vatican page loads with correct date/time"
echo -e "✅ Form fields auto-fill with names"
echo -e "✅ Booking proceeds automatically"

echo -e "\n${BLUE}🔍 DEBUGGING${NC}"
echo -e "────────────────────────────────────────────────────────────────────────────────"
echo -e "If nothing happens:"
echo -e "1. Open Chrome DevTools (${YELLOW}F12${NC})"
echo -e "2. Go to ${YELLOW}Console${NC} tab"
echo -e "3. Look for extension logs (should show 'Backend Listener Mode')"
echo -e "4. Check ${YELLOW}Network${NC} tab for API calls to localhost:8000"
echo -e ""
echo -e "If incognito window doesn't open:"
echo -e "1. Verify '${YELLOW}Allow in incognito${NC}' is enabled (Step 1)"
echo -e "2. Check extension console for errors"
echo -e "3. Try manually: chrome://extensions/ → Details → Allow in incognito"

echo -e "\n${BLUE}📝 MANUAL API TEST${NC}"
echo -e "────────────────────────────────────────────────────────────────────────────────"
echo -e "You can manually check available slots:"
echo -e "${YELLOW}curl http://localhost:8000/api/v1/available-slots/?agency_id=${AGENCY_ID}${NC}"

echo -e "\n${BLUE}🗑️  CLEANUP${NC}"
echo -e "────────────────────────────────────────────────────────────────────────────────"
echo -e "To clean up test data after testing:"
echo -e "${YELLOW}./test_august_13_booking.sh --cleanup${NC}"

echo -e "\n================================================================================"
echo -e "${GREEN}🎉 READY TO TEST!${NC}"
echo -e "================================================================================"
echo -e "\nFollow the steps above and watch the automated booking in action!"
echo -e ""
