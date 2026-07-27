#!/usr/bin/env python3
"""
INSTANT SNIPER - Immediate Slot Acquisition System
==================================================

Enhanced version that immediately reserves slots when detected,
bypassing notifications and going straight to holding.

Uses existing: 
- Proxy rotation system
- Session management  
- Vatican API endpoints from HAR files
- reCAPTCHA solving infrastructure
"""

import os
import sys
import logging
import time
from datetime import datetime, timedelta

# Add the backend directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

from celery import shared_task
from django.utils import timezone
from django.core.cache import cache

# Import your existing modules
from backend.monitors.tasks_sweep import _search_and_timeavail, _get_proxy
from backend.monitors.hold_manager import hold_slot
from backend.monitors.models import MonitorTask, HeldSlot

logger = logging.getLogger(__name__)

# Vatican API configuration from your HAR analysis
BASE = 'https://tickets.museivaticani.va'
HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'X-Requested-With': 'XMLHttpRequest', 
    'Referer': f'{BASE}/',
    'Origin': BASE,
    'Content-Type': 'application/json',
}

def _get_sniper_task():
    """Get or create the sniper monitor task."""
    task, created = MonitorTask.objects.get_or_create(
        name="INSTANT-SNIPER",
        defaults={
            'site': 'vatican',
            'tier': 'sniper',
            'visitors': 2,
            'is_active': True,
            'agency_id': 1  # Default agency
        }
    )
    return task

def _immediate_snipe(session, ticket_id, date, slot_time, slot_info, proxy_str):
    """Immediately attempt to hold a detected slot."""
    try:
        slot_id = slot_info.get('id')
        if not slot_id:
            logger.warning(f"No slot ID for {date} {slot_time}")
            return False
        
        logger.info(f"🎯 SNIPING: {date} {slot_time} (ID: {slot_id})")
        
        # Use your existing hold_slot function with turbo mode
        held_slot = hold_slot(
            task=_get_sniper_task(),
            date=date,
            slot_id=slot_id,
            slot_time=slot_time,
            ticket_id=ticket_id,
            ticket_name=slot_info.get('name', 'Biglietto Intero'),
            visitors=2,  # Default to 2 visitors for speed
            proxy_str=proxy_str,
            immediate_mode=True  # Bypass queues for instant action
        )
        
        if held_slot and held_slot.status == 'held':
            logger.info(f"✅ SNIPE SUCCESS: Held slot #{held_slot.id} for {date} {slot_time}")
            
            # Immediate payment readiness check
            _validate_payment_readiness(held_slot)
            
            return True
        else:
            logger.warning(f"❌ SNIPE FAILED: {date} {slot_time}")
            return False
            
    except Exception as e:
        logger.error(f"💥 SNIPE ERROR: {date} {slot_time} - {e}")
        return False

def _validate_payment_readiness(held_slot):
    """Quick validation that the held slot can proceed to payment."""
    try:
        # Check session freshness (from your continuous_april_holding.py)
        if held_slot.last_keepalive_at:
            minutes_since = (timezone.now() - held_slot.last_keepalive_at).total_seconds() / 60
            if minutes_since > 5:  # More aggressive than 10-minute default
                logger.warning(f"⚠️ Session stale: {minutes_since:.1f}m since keepalive")
        
        # TODO: Add immediate epay link generation here
        
    except Exception as e:
        logger.error(f"Payment validation error: {e}")

@shared_task(name="instant_sniper_scan", queue="vatican", priority=0)  # Highest priority
def instant_sniper_scan():
    """
    Turbo-charged scanner that immediately snipes detected slots.
    Runs every 15 seconds for maximum responsiveness.
    """
    # Get target dates from your existing configuration
    target_dates_str = os.getenv('SWEEP_TARGET_DATES', '')
    if target_dates_str:
        dates = [d.strip() for d in target_dates_str.split(',') if d.strip()]
    else:
        # Auto-generate: all days in April + May 2026 (from your tasks_sweep.py)
        dates = []
        for month in [4, 5]:
            for day in range(1, 32):
                try:
                    d = datetime(2026, month, day)
                    if d.date() >= datetime.now().date():
                        dates.append(d.strftime('%d/%m/%Y'))
                except ValueError:
                    pass
    
    if not dates:
        logger.warning("No target dates configured for sniper")
        return "No target dates"
    
    logger.info(f"🔫 INSTANT SNIPER: Scanning {len(dates)} target dates")
    
    snipe_count = 0
    proxy_str = _get_proxy()
    
    for date in dates:
        try:
            # Use your existing search function
            session, ticket_id, open_slots = _search_and_timeavail(date, 2, proxy_str)
            
            if not open_slots:
                continue
                
            for slot in open_slots:
                slot_time = slot.get('time', '')
                
                # Check if we already processed this slot recently
                slot_key = f"snipe_processed:{date}:{slot_time}"
                if cache.get(slot_key):
                    continue
                
                # Immediate snipe attempt
                success = _immediate_snipe(session, ticket_id, date, slot_time, slot, proxy_str)
                
                if success:
                    snipe_count += 1
                    # Prevent re-processing for 2 minutes
                    cache.set(slot_key, True, timeout=120)
                
                # Small delay between slot attempts
                time.sleep(0.1)
                
        except Exception as e:
            logger.error(f"Error scanning {date}: {e}")
        
        # Small delay between dates
        time.sleep(0.2)
    
    if snipe_count > 0:
        logger.info(f"🎯 INSTANT SNIPER: Successfully acquired {snipe_count} slots!")
    else:
        logger.debug("INSTANT SNIPER: No new slots acquired")
    
    return f"Scanned {len(dates)} dates, acquired {snipe_count} slots"

# Celery beat schedule addition
def should_add_to_celery_beat():
    """Add this to your celery.py beat_schedule:
    
    from instant_sniper import instant_sniper_scan
    
    beat_schedule = {
        'instant-sniper-scan': {
            'task': 'instant_sniper_scan',
            'schedule': 15.0,  # Every 15 seconds
            'options': {'priority': 0}  # Highest priority
        },
    }
    """
    pass

if __name__ == "__main__":
    # Manual test mode
    logging.basicConfig(level=logging.INFO)
    print("Testing instant sniper...")
    result = instant_sniper_scan()
    print(f"Result: {result}")