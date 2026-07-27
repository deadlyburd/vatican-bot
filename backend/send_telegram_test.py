
import asyncio
import logging
from datetime import datetime
import sys
import os

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.monitors.notification_utils import format_vatican_notification

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_notification_format():
    date = "26/03/2026"
    ticket_name = "Musei Vaticani - Biglietti d'ingresso"
    ticket_id = "123456"
    slots = [
        {"time": "09:00", "availability": "AVAILABLE"},
        {"time": "10:00", "availability": "AVAILABLE"},
        {"time": "11:00", "availability": "AVAILABLE"}
    ]
    preferred_times = ["09:00"]
    language = "ITA"
    visitors = 2
    check_method = "god-tier"
    
    logger.info("--- Testing Notification Format ---")
    message = format_vatican_notification(
        date=date,
        ticket_name=ticket_name,
        ticket_id=ticket_id,
        slots=slots,
        preferred_times=preferred_times,
        language=language,
        visitors=visitors,
        check_method=check_method
    )
    
    print("\n" + "="*40)
    print(message)
    print("="*40 + "\n")
    
    if "Checked at:" in message and "(Rome)" in message:
        logger.info("✅ SUCCESS: Message includes monitoring time")
    else:
        logger.error("❌ FAILURE: Message missing monitoring time")

if __name__ == "__main__":
    test_notification_format()
