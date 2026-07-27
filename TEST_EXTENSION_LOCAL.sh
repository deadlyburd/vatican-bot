#!/bin/bash

# Quick Test Script for Extension with Regular Windows
# This tests the extension locally before deploying to server

echo "========================================="
echo "🧪 Testing Vatican Extension Locally"
echo "========================================="
echo ""

# Check if Chrome is already running
if pgrep -f "google-chrome.*browser-extension" > /dev/null; then
    echo "⚠️  Chrome is already running with the extension."
    echo "   Please close it first or reload the extension at chrome://extensions/"
    echo ""
    read -p "Press Enter to continue after reloading the extension..."
else
    echo "🚀 Launching Chrome with extension..."
    echo ""
    
    # Launch Chrome with extension
    google-chrome \
        --load-extension=/home/abiilesh/Documents/bot/bot/browser-extension \
        --disable-extensions-except=/home/abiilesh/Documents/bot/bot/browser-extension \
        --user-data-dir=/home/abiilesh/Documents/bot/bot/test_profile \
        --no-first-run \
        https://tickets.museivaticani.va/ &
    
    echo "✅ Chrome launched!"
    echo ""
    sleep 3
fi

echo "📋 Next Steps:"
echo ""
echo "1. Click the extension icon (Vatican Ticket Monitor)"
echo "2. Configure:"
echo "   - Backend URL: http://localhost:8000"
echo "   - Mode: 🚀 Backend Listener"
echo "   - Click 'Start Monitoring'"
echo ""
echo "3. In another terminal, trigger a test booking:"
echo "   cd /home/abiilesh/Documents/bot/bot"
echo "   docker-compose exec backend python -c \\"
echo "     from backend.services.slot_manager import SlotManager; \\"
echo "     SlotManager.add_available_slot({ \\"
echo "       'id': 'TEST-SLOT-001', \\"
echo "       'date': '13/08/2026', \\"
echo "       'time': '17:00', \\"
echo "       'ticket_id': '2129030053', \\"
echo "       'ticket_name': 'Musei Vaticani - Biglietti d\\'ingresso', \\"
echo "       'visitors': 2, \\"
echo "       'adult_count': 2, \\"
echo "       'child_count': 0, \\"
echo "       'language': '', \\"
echo "       'profile': {'first_name': 'Test', 'last_name': 'User', 'email': 'test@example.com'}, \\"
echo "       'participants': [{'first_name': 'Test', 'last_name': 'User'}, {'first_name': 'Jane', 'last_name': 'Doe'}] \\"
echo "     })\\"
echo ""
echo "4. Watch for REGULAR windows to open (not incognito!)"
echo "   - Windows should open automatically"
echo "   - Forms should auto-fill with names"
echo "   - No incognito permission needed"
echo ""
echo "========================================="
echo "✅ Test Setup Complete"
echo "========================================="
