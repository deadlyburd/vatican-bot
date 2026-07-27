"""
Enhanced Vatican Hold Manager with Error-Free Reservation
=========================================================
Integrates the error-free reservation handler to fix 500 errors.
"""
import logging
import requests
import time
import os
from django.utils import timezone
from .epay_ssl import make_vatican_session
from .error_free_reservation import error_free_reservation

logger = logging.getLogger(__name__)

BASE = 'https://tickets.museivaticani.va'
HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': f'{BASE}/',
    'Origin': BASE,
    'Content-Type': 'application/json',
}


def complete_reservation_error_free(held_slot, participants=None, representative=None):
    """
    Complete reservation using the error-free handler.
    
    Returns: (success: bool, response_data: dict)
    """
    logger.info(f"🎯 Completing reservation for HeldSlot #{held_slot.id}")
    
    try:
        # Use the error-free reservation handler
        success, result = error_free_reservation.complete_reservation(
            held_slot, participants, representative
        )
        
        if success:
            logger.info(f"✅ Reservation completed: {result['reference']}")
            # Update held slot status
            held_slot.status = 'paying'
            held_slot.payment_url = result['epay_url']
            held_slot.save()
            
            return True, result
        else:
            logger.error(f"❌ Reservation failed: {result.get('error', 'Unknown error')}")
            return False, result
            
    except Exception as e:
        logger.error(f"❌ Reservation exception: {e}")
        return False, {'error': str(e), 'exception': True}


def generate_epay_url_error_free(held_slot, participants=None, representative=None):
    """
    Generate epay URL using error-free reservation.
    
    Returns: epay_url or None
    """
    success, result = complete_reservation_error_free(held_slot, participants, representative)
    
    if success:
        return result.get('epay_url')
    else:
        logger.error(f"Failed to generate epay URL: {result.get('error')}")
        return None


def hold_with_dynamic_injection_error_free(task, slot_data, injection_config=None):
    """
    Enhanced hold with dynamic injection using error-free reservation.
    """
    from .models import BuyerProfile, HeldSlot
    
    # Extract slot data
    date = slot_data.get('date')
    slot_id = slot_data.get('slot_id')
    slot_time = slot_data.get('slot_time')
    ticket_id = slot_data.get('ticket_id')
    ticket_name = slot_data.get('ticket_name')
    visitors = slot_data.get('visitors', task.visitors)
    
    # Get base profile
    try:
        profile = BuyerProfile.objects.get(agency=task.agency)
    except BuyerProfile.DoesNotExist:
        logger.error(f"❌ No buyer profile for agency {task.agency.name}")
        return None
    
    # Use dynamic participants or fallback to profile
    if injection_config and injection_config.participant_overrides:
        participants = injection_config.participant_overrides
        logger.info(f"🔧 Using dynamic injection: {len(participants)} participants")
    else:
        # Generate proper participants to avoid blank names
        participants = error_free_reservation.generate_participant_names(visitors, task.agency)
        logger.info(f"🔧 Generated {len(participants)} participants")
    
    # Standard hold first
    held = hold_slot(task, date, slot_id, slot_time, ticket_id, ticket_name, visitors)
    
    if not held:
        logger.error("❌ Failed to hold slot")
        return None
    
    # If we have an injection config and direct snipe is requested
    if injection_config and injection_config.action == 'snipe':
        try:
            # Use error-free reservation for sniping
            success, result = complete_reservation_error_free(held, participants)
            
            if success:
                logger.info(f"🎯 Direct snipe completed: {result['reference']}")
                injection_config.mark_used({'status': 'snipe_completed', 'reference': result['reference']})
                
                # Update held slot
                held.status = 'paying'
                held.payment_url = result['epay_url']
                held.save()
            else:
                logger.error(f"❌ Direct snipe failed: {result.get('error')}")
                injection_config.mark_used({'status': f'snipe_failed: {result.get("error")}'})
                
        except Exception as e:
            logger.error(f"❌ Direct snipe exception: {e}")
            injection_config.mark_used({'status': f'snipe_exception: {e}'})
    
    elif injection_config and injection_config.action == 'epay':
        # Generate epay URL using error-free reservation
        try:
            epay_url = generate_epay_url_error_free(held, participants)
            
            if epay_url:
                logger.info(f"✅ Epay URL generated: {epay_url[:50]}...")
                held.payment_url = epay_url
                held.save()
                injection_config.mark_used({'epay_url': epay_url})
            else:
                logger.error("❌ Failed to generate epay URL")
                injection_config.mark_used({'status': 'epay_failed'})
                
        except Exception as e:
            logger.error(f"❌ Epay generation exception: {e}")
            injection_config.mark_used({'status': f'epay_exception: {e}'})
    
    return held


# Import original functions and override
try:
    from .hold_manager import hold_slot, _make_session, _get_serverid, _load_notes
    logger.info("✅ Imported original hold_manager functions")
except ImportError as e:
    logger.error(f"❌ Failed to import hold_manager: {e}")
    # Fallback implementations would go here
    def hold_slot(*args, **kwargs):
        logger.error("hold_slot not available")
        return None