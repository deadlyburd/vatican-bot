"""
Continuous April Slot Holding System with Payment Capability
=============================================================

This system enables forever-holding of Vatican slots by automatically re-acquiring
slots before the 24-hour Vatican expiration. It addresses Docker session issues
and ensures slots remain available for payment.

Key Features:
1. Automatic slot re-acquisition at 23-hour mark
2. Session freshness validation and recovery
3. Docker-compatible session management
4. Payment-ready slot state maintenance
5. Proxy rotation for maximum holding capacity
"""

import os
import sys
import time
import logging
import json
from datetime import datetime, timedelta

# Add the backend directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
import django
django.setup()

from monitors.models import HeldSlot, MonitorTask
from monitors.hold_manager import hold_slot, keepalive_slot, _fresh_re_hold
from monitors.tasks_search_api import get_proxy_str

logger = logging.getLogger(__name__)


def check_slot_expiry(held_slot):
    """Check if a slot is approaching 24-hour expiry and needs re-holding."""
    age_hours = held_slot.hold_duration_hours()
    
    # If approaching 23 hours, re-hold the slot
    if age_hours >= 23:
        logger.info(f"🔄 Slot {held_slot.id} approaching 24-hour expiry - re-holding...")
        return re_hold_slot(held_slot)
    
    return True


def re_hold_slot(held_slot):
    """Re-acquire a slot using fresh session and updated slot/ticket IDs."""
    try:
        # Get fresh proxy for this re-hold attempt
        proxy_str, proxy_obj = get_proxy_str('vatican')
        
        # Create fresh hold with current task parameters
        fresh_hold = hold_slot(
            task=held_slot.task,
            date=held_slot.date,
            slot_id=held_slot.slot_id,  # Will be refreshed by hold_slot
            slot_time=held_slot.slot_time,
            ticket_id=held_slot.ticket_id,  # Will be refreshed by hold_slot
            ticket_name=held_slot.ticket_name,
            visitors=held_slot.visitors,
            proxy_str=proxy_str
        )
        
        if fresh_hold:
            logger.info(f"✅ Successfully re-held slot {held_slot.id} -> {fresh_hold.id}")
            
            # Mark old slot as released
            held_slot.status = 'released'
            held_slot.released_at = datetime.now()
            held_slot.save(update_fields=['status', 'released_at'])
            
            return True
        else:
            logger.warning(f"❌ Failed to re-hold slot {held_slot.id}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Exception during re-hold of slot {held_slot.id}: {e}")
        return False


def validate_session_freshness(held_slot):
    """Validate that the session is still fresh and capable of payment."""
    try:
        # Check if session is stale (more than 10 minutes since last keepalive)
        if held_slot.last_keepalive_at:
            minutes_since_keepalive = (datetime.now() - held_slot.last_keepalive_at.replace(tzinfo=None)).total_seconds() / 60
            if minutes_since_keepalive > 10:
                logger.warning(f"⚠️ Session stale for HeldSlot #{held_slot.id}: {minutes_since_keepalive:.1f} min since keepalive")
                
                # Attempt to refresh the session
                if _fresh_re_hold(held_slot):
                    logger.info(f"✅ Successfully refreshed stale session for HeldSlot #{held_slot.id}")
                    return True
                else:
                    logger.error(f"❌ Failed to refresh stale session for HeldSlot #{held_slot.id}")
                    return False
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Exception validating session freshness for slot {held_slot.id}: {e}")
        return False


def continuous_hold_monitor():
    """Main monitoring loop for continuous slot holding."""
    logger.info("🚀 Starting continuous slot holding monitor...")
    
    while True:
        try:
            # Get all active held slots
            active_holds = HeldSlot.objects.filter(status='held')
            
            if not active_holds.exists():
                logger.info("💤 No active holds - sleeping for 5 minutes")
                time.sleep(300)  # 5 minutes
                continue
            
            logger.info(f"🔍 Checking {active_holds.count()} active holds...")
            
            for hold in active_holds:
                try:
                    # Check session freshness first
                    if not validate_session_freshness(hold):
                        logger.warning(f"⚠️ Session validation failed for hold {hold.id}")
                        continue
                    
                    # Check if slot needs re-holding due to expiry
                    if not check_slot_expiry(hold):
                        logger.warning(f"⚠️ Slot expiry check failed for hold {hold.id}")
                        continue
                    
                    # Perform regular keepalive
                    if keepalive_slot(hold):
                        logger.debug(f"💓 Keepalive successful for hold {hold.id}")
                    else:
                        logger.warning(f"⚠️ Keepalive failed for hold {hold.id}")
                        
                except Exception as e:
                    logger.error(f"❌ Error processing hold {hold.id}: {e}")
                    continue
            
            # Sleep for 5 minutes between checks
            time.sleep(300)
            
        except Exception as e:
            logger.error(f"❌ Error in continuous hold monitor: {e}")
            time.sleep(60)  # Shorter sleep on error


def get_payment_ready_slots():
    """Get all slots that are ready for payment (fresh sessions)."""
    payment_ready = []
    
    for hold in HeldSlot.objects.filter(status='held'):
        if validate_session_freshness(hold):
            payment_ready.append(hold)
    
    return payment_ready


def hold_specific_slot(task_id, date, slot_time, visitors=2):
    """Hold a specific slot with continuous holding enabled."""
    try:
        task = MonitorTask.objects.get(id=task_id)
        
        # Get proxy for this hold
        proxy_str, proxy_obj = get_proxy_str('vatican')
        
        # Hold the slot (slot_id and ticket_id will be resolved automatically)
        held = hold_slot(
            task=task,
            date=date,
            slot_id='',  # Will be resolved by hold_slot
            slot_time=slot_time,
            ticket_id='',  # Will be resolved by hold_slot
            ticket_name='Musei Vaticani e Cappella Sistina',
            visitors=visitors,
            proxy_str=proxy_str
        )
        
        if held:
            logger.info(f"✅ Successfully held slot: {date} {slot_time} for {visitors} visitors")
            return held
        else:
            logger.error(f"❌ Failed to hold slot: {date} {slot_time}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Exception holding slot {date} {slot_time}: {e}")
        return None


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('continuous_holding.log')
        ]
    )
    
    logger.info("🎯 Starting Vatican Continuous Slot Holding System")
    logger.info("💡 Features: Auto re-hold at 23h, Session freshness validation, Payment readiness")
    
    try:
        continuous_hold_monitor()
    except KeyboardInterrupt:
        logger.info("🛑 Continuous holding stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error in continuous holding: {e}")
        sys.exit(1)