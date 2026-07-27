"""
ULTRA-FAST Direct API Payment for Vatican
===========================================

Direct API integration for fastest possible payment completion.
Bypasses browsers entirely - pure API speed.
"""

import os
import sys
import logging
import time
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import your existing modules
from .epay_ssl import make_vatican_session
from .hold_manager import _build_recap_body
from .turnstile_pool import get_turnstile_token

# Vatican API endpoints
BASE_URL = 'https://tickets.museivaticani.va'
EPAY_URL = 'https://epay.catholica.va/pay/SIV001/upp/auth/start.page'

# Headers for maximum speed
TURBO_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'Origin': BASE_URL,
    'Referer': f'{BASE_URL}/home/checkout',
    'Content-Type': 'application/json',
    'Connection': 'keep-alive',  # Keep connection alive for speed
}

def ultra_fast_payment(held_slot, card_details):
    """
    Complete payment in milliseconds using direct API calls.
    
    Args:
        held_slot: HeldSlot object with session cookies
        card_details: Dict with card information
        
    Returns: True if payment successful, False otherwise
    """
    start_time = time.time()
    
    try:
        # Step 1: Create session with EXACT same cookies as the hold
        session = make_vatican_session()
        session.headers.update(TURBO_HEADERS)
        
        # Set the precise cookies from the held slot
        session.cookies.set('JSESSIONID', held_slot.jsessionid, domain='tickets.museivaticani.va')
        session.cookies.set('ticketmv', held_slot.ticketmv or '01', domain='tickets.museivaticani.va')
        
        # Step 2: Verify session is still valid (milliseconds)
        verify_start = time.time()
        verify_response = session.get(
            f'{BASE_URL}/api/config/initValues',
            timeout=5
        )
        
        if verify_response.status_code != 200:
            logger.error(f"Session invalid: {verify_response.status_code}")
            return False
        
        logger.info(f"✅ Session verified in {((time.time() - verify_start) * 1000):.2f}ms")
        
        # Step 3: Get Turnstile token (pre-solved for speed)
        token_start = time.time()
        recaptcha_token = get_turnstile_token()  # Your existing token pool
        logger.info(f"✅ Token acquired in {((time.time() - token_start) * 1000):.2f}ms")
        
        # Step 4: Build reservation payload
        reservation_data = {
            'recaptcha': recaptcha_token,
            'lang': 'it',
            'recapId': held_slot.recap_id,
            'visitorNum': held_slot.visitors,
            'visitId': str(held_slot.ticket_id),
            'visitTypeId': 1,
            'tickets': [{
                'ticketId': int(held_slot.ticket_id),
                'quantity': held_slot.visitors,
                'price': float(held_slot.total_price) / held_slot.visitors if held_slot.total_price else 25.0
            }],
            'services': [],
            'representativeUser': _get_buyer_profile(held_slot),
            'participantUser': []
        }
        
        # Step 5: Make reservation (critical speed step)
        reserve_start = time.time()
        reservation_response = session.post(
            f'{BASE_URL}/api/visit/reservation',
            json=reservation_data,
            timeout=10
        )
        
        if reservation_response.status_code != 200:
            logger.error(f"Reservation failed: {reservation_response.status_code}")
            logger.error(f"Response: {reservation_response.text}")
            return False
        
        logger.info(f"✅ Reservation completed in {((time.time() - reserve_start) * 1000):.2f}ms")
        
        # Step 6: Direct payment API call
        payment_start = time.time()
        
        # Format payment data according to Vatican's requirements
        payment_data = _format_payment_data(card_details, held_slot)
        
        # Use the same session (critical for cookies)
        payment_response = session.post(
            EPAY_URL,
            data=payment_data,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': f'{BASE_URL}/home/checkout/confirm/it/{held_slot.recap_id}',
                'Origin': BASE_URL
            },
            timeout=15
        )
        
        # Step 7: Verify payment success
        if payment_response.status_code in [200, 302]:
            total_time = (time.time() - start_time) * 1000
            logger.info(f"🎯 PAYMENT COMPLETED in {total_time:.2f}ms")
            
            # Parse payment confirmation
            if 'success' in payment_response.text.lower() or 'grazie' in payment_response.text.lower():
                return True
            
            # Check for redirect to success page
            if payment_response.headers.get('Location', '').endswith('/success'):
                return True
        
        logger.error(f"Payment failed: {payment_response.status_code}")
        logger.error(f"Response: {payment_response.text[:500]}")
        return False
        
    except Exception as e:
        logger.error(f"Ultra-fast payment error: {e}")
        return False


def _get_buyer_profile(held_slot):
    """Get buyer profile details for payment."""
    from .models import BuyerProfile
    
    try:
        profile = BuyerProfile.objects.get(agency=held_slot.task.agency)
        return {
            'name': profile.first_name,
            'surname': profile.last_name,
            'email': profile.email,
            'phone': profile.phone,
            'country': profile.country
        }
    except BuyerProfile.DoesNotExist:
        # Fallback to generic details
        return {
            'name': 'Customer',
            'surname': 'Name', 
            'email': 'booking@agency.com',
            'phone': '+390000000000',
            'country': 'IT'
        }


def _format_payment_data(card_details, held_slot):
    """Format card details for Vatican payment API."""
    return {
        'cardNumber': card_details['number'],
        'expiryDate': card_details['expiry'],
        'cvv': card_details['cvv'],
        'cardholderName': card_details.get('name', 'CARDHOLDER'),
        'amount': str(held_slot.total_price or '5000'),  # In cents
        'currency': 'EUR',
        'orderReference': held_slot.recap_id or f'MV{int(time.time())}',
        'description': f'Vatican Tickets - {held_slot.date} {held_slot.slot_time}',
        'returnUrl': f'{BASE_URL}/epay/success',
        'cancelUrl': f'{BASE_URL}/epay/cancel'
    }


def batch_ultra_fast_payment(hold_ids, card_details):
    """Process multiple payments in parallel for maximum speed."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from .models import HeldSlot
    
    results = {}
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Submit all payment tasks
        future_to_hold = {
            executor.submit(ultra_fast_payment, HeldSlot.objects.get(id=hold_id), card_details): hold_id
            for hold_id in hold_ids
        }
        
        # Process results as they complete
        for future in as_completed(future_to_hold):
            hold_id = future_to_hold[future]
            try:
                results[hold_id] = future.result()
            except Exception as e:
                results[hold_id] = False
                logger.error(f"Payment failed for hold {hold_id}: {e}")
    
    return results


# Celery task for automatic payment
from celery import shared_task

@shared_task(name='ultra_fast_payment_task', queue='vatican_payment')
def ultra_fast_payment_task(hold_id, card_profile='default'):
    """Celery task for ultra-fast payment processing."""
    from .models import HeldSlot
    
    try:
        held_slot = HeldSlot.objects.get(id=hold_id)
        
        # Get card details from your secure storage
        card_details = get_card_details(card_profile)
        
        # Execute ultra-fast payment
        success = ultra_fast_payment(held_slot, card_details)
        
        if success:
            held_slot.status = 'paid'
            held_slot.save()
            
            # Send instant confirmation
            send_payment_confirmation(held_slot)
            
            return True
        else:
            # Mark for retry or manual intervention
            held_slot.status = 'payment_failed'
            held_slot.save()
            return False
            
    except Exception as e:
        logger.error(f"Payment task failed for hold {hold_id}: {e}")
        return False


def get_card_details(profile_name='default'):
    """Retrieve card details from secure storage."""
    # Implement your secure card storage here
    # This could be from encrypted database, environment variables, or secure config
    
    cards = {
        'default': {
            'number': '4111111111111111',  # Replace with actual card
            'expiry': '12/26',
            'cvv': '123',
            'name': 'YOUR NAME'
        },
        'backup': {
            'number': '4222222222222222',
            'expiry': '06/25', 
            'cvv': '456',
            'name': 'BACKUP CARD'
        }
    }
    
    return cards.get(profile_name, cards['default'])


def send_payment_confirmation(held_slot):
    """Payment confirmation — DISABLED: only slot monitoring sends to agencies."""
    # ❌ DISABLED
    return