
import os
import sys
import django
import logging

# d:/bot/travelagenntbot/backend
current_dir = os.path.dirname(os.path.abspath(__file__)) 

# We are INSIDE 'backend' directory.
# Django settings are likely at 'core.settings' or just 'settings' if 'backend' is the project root.
# Looking at the LS output:
# backend/
#   core/
#     settings.py

# So the project root is 'backend' (which contains manage.py)
sys.path.insert(0, current_dir)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

django.setup()

from monitors.tasks import send_daily_summary

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_daily_summary():
    """Test the daily summary task"""
    logger.info("🧪 Testing daily summary report...")
    try:
        result = send_daily_summary()
        logger.info(f"✅ Result: {result}")
    except Exception as e:
        logger.error(f"❌ Failed: {e}")

if __name__ == "__main__":
    test_daily_summary()
