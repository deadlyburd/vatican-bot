
import asyncio
import logging
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import notification utils
from monitors.notification_utils import send_telegram_signal, format_vatican_notification

def test_telegram_sending():
    """Test sending a Telegram notification"""
    logger.info("🧪 Testing Telegram notification sending...")
    
    # Check if TELEGRAM_BOT_TOKEN is set
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("❌ TELEGRAM_BOT_TOKEN environment variable is not set!")
        return
    
    logger.info(f"✅ TELEGRAM_BOT_TOKEN is set (starts with {token[:5]}...)")
    
    # Prompt for Chat ID if not provided
    chat_id = os.getenv("TEST_CHAT_ID")
    if not chat_id:
        # Default to a placeholder or ask user to set it
        # For this test, we'll try to find an agency with a chat_id from DB
        try:
            # Setup Django environment correctly
            # We are in d:/bot/travelagenntbot/backend
            # We need to add d:/bot/travelagenntbot to path to import backend.settings
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            
            # Ensure backend is not in sys.path as a root, but project_root is
            if current_dir in sys.path:
                sys.path.remove(current_dir)
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
            
            # Also add current directory so we can import 'core' if needed directly
            sys.path.insert(0, current_dir)
            
            os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
            
            import django
            django.setup()
            
            from monitors.models import Agency
            agency = Agency.objects.filter(telegram_chat_id__isnull=False).exclude(telegram_chat_id='').first()
            
            if agency:
                chat_id = agency.telegram_chat_id
                logger.info(f"📋 Found agency '{agency.name}' with chat_id: {chat_id}")
            else:
                logger.error("❌ No agencies found with telegram_chat_id in database.")
                logger.info("Please set TEST_CHAT_ID environment variable to test manually.")
                return
        except Exception as e:
            logger.error(f"❌ Failed to query database: {e}")
            return

    # Create a test message
    message = format_vatican_notification(
        date="26/03/2026",
        ticket_name="TEST NOTIFICATION",
        ticket_id="123456",
        slots=[{"time": "10:00"}, {"time": "14:00"}],
        preferred_times=["10:00"],
        language="ENG",
        visitors=2,
        check_method="test"
    )
    
    # Send message
    logger.info(f"📤 Sending test message to {chat_id}...")
    success = send_telegram_signal(chat_id, message)
    
    if success:
        logger.info("✅ Message sent successfully!")
    else:
        logger.error("❌ Failed to send message.")

if __name__ == "__main__":
    test_telegram_sending()
