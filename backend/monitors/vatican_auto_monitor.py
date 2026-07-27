"""
Vatican Auto Monitor with Complete Booking
===========================================
Monitors Vatican API and automatically completes bookings when slots are available
"""

import logging
import asyncio
from datetime import datetime
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="monitor_and_auto_book", queue="vatican")
def monitor_and_auto_book():
    """
    Main monitoring task that:
    1. Checks Vatican API for availability
    2. Automatically books when slots are found
    3. Updates Google Sheets with checkout link
    
    Runs every 5-10 minutes
    """
    return asyncio.run(_monitor_and_auto_book_async())


async def _monitor_and_auto_book_async():
    """Async implementation of monitoring + auto booking"""
    from backend.models import VaticanTask
    from backend.services.vatican_auto_booker import get_auto_booker
    import requests
    
    logger.info("🔍 Starting Vatican auto-monitor...")
    
    # Get all pending/monitoring tasks
    tasks = VaticanTask.objects.filter(
        status__in=['pending', 'monitoring'],
        target_date__gte=timezone.now().date()
    ).order_by('target_date', 'priority')
    
    if not tasks.exists():
        logger.info("   No active tasks to monitor")
        return "No tasks"
    
    logger.info(f"   Found {tasks.count()} tasks to check")
    
    auto_booker = get_auto_booker()
    checked = 0
    booked = 0
    
    for task in tasks[:20]:  # Limit to 20 tasks per run to avoid rate limits
        try:
            logger.info(f"\n📋 Checking: {task.booking_id}")
            logger.info(f"   Date: {task.target_date.strftime('%d/%m/%Y')}")
            logger.info(f"   Visitors: {task.visitors}")
            
            # Check availability using Vatican API
            available_slots = await _check_availability(task)
            
            if available_slots:
                logger.info(f"   ✅ Found {len(available_slots)} available slots!")
                logger.info(f"   Slots: {', '.join(available_slots[:5])}")
                
                # Update task status
                task.status = 'available'
                task.available_slots = ','.join(available_slots)
                task.last_checked = timezone.now()
                task.save()
                
                # AUTO-BOOK: Pick best slot (closest to target time)
                best_slot = _pick_best_slot(available_slots, task.target_time)
                logger.info(f"   🎯 Auto-booking slot: {best_slot}")
                
                # Run automated booking
                result = await auto_booker.book_ticket_automated(task, best_slot)
                
                if result.get('success'):
                    logger.info(f"   ✅ BOOKING COMPLETE!")
                    logger.info(f"   Reference: {result.get('reference')}")
                    logger.info(f"   Checkout: {result.get('epay_url')}")
                    booked += 1
                else:
                    logger.error(f"   ❌ Booking failed: {result.get('error')}")
            else:
                logger.info(f"   ⏳ No slots available yet")
                task.status = 'monitoring'
                task.last_checked = timezone.now()
                task.save()
            
            checked += 1
            
            # Rate limiting: wait between checks
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"   ❌ Error checking {task.booking_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    summary = f"Checked {checked} tasks, booked {booked}"
    logger.info(f"\n✅ Monitor complete: {summary}")
    return summary


async def _check_availability(task) -> list:
    """
    Check Vatican API for available time slots
    
    Returns:
        list of available time slots (HH:MM format)
    """
    import requests
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    # Format date for API
    api_date = task.target_date.strftime('%d/%m/%Y')
    
    # Determine tag based on ticket type
    tag = 'MV-Visite-Guidate' if task.ticket_type == 1 else 'MV-Biglietti'
    
    # Step 1: Search API to get fresh ticket IDs
    search_url = "https://tickets.museivaticani.va/api/search/resultPerTag"
    search_params = {
        'lang': 'it',
        'visitorNum': str(task.visitors),
        'visitDate': api_date,
        'area': '1',
        'who': '',
        'page': '0',
        'tag': tag
    }
    
    search_headers = {
        'Accept': 'application/json, text/plain, */*',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': 'https://tickets.museivaticani.va/'
    }
    
    try:
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.get(search_url, params=search_params, headers=search_headers, timeout=10)
        )
        
        if response.status_code != 200:
            logger.warning(f"   Search API returned {response.status_code}")
            return []
        
        data = response.json()
        tickets = data.get('visits', [])
        
        if not tickets:
            logger.warning(f"   No tickets found in search results")
            return []
        
        # Find matching ticket by name
        target_ticket = None
        for ticket in tickets:
            if ticket.get('availability') in ['AVAILABLE', 'LOW_AVAILABILITY']:
                # Match standard tickets
                if task.ticket_type == 0 and 'ingresso' in ticket.get('name', '').lower():
                    target_ticket = ticket
                    break
                # Match guided tours
                elif task.ticket_type == 1 and 'guidata' in ticket.get('name', '').lower():
                    target_ticket = ticket
                    break
        
        if not target_ticket:
            logger.info(f"   No available tickets matching criteria")
            return []
        
        ticket_id = str(target_ticket['id'])
        jsessionid = response.cookies.get('JSESSIONID')
        
        if not jsessionid:
            logger.warning(f"   No JSESSIONID in response")
            return []
        
        # Step 2: Check time availability
        timeavail_url = "https://tickets.museivaticani.va/api/visit/timeavail"
        timeavail_params = {
            'lang': 'it',
            'visitLang': task.language if task.language else '',
            'visitTypeId': ticket_id,
            'visitorNum': str(task.visitors),
            'visitDate': api_date
        }
        
        timeavail_headers = {
            'Accept': 'application/json, text/plain, */*',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'https://tickets.museivaticani.va/',
            'Cookie': f'JSESSIONID={jsessionid}'
        }
        
        time_response = await loop.run_in_executor(
            None,
            lambda: requests.get(timeavail_url, params=timeavail_params, headers=timeavail_headers, timeout=10)
        )
        
        if time_response.status_code != 200:
            logger.warning(f"   Time API returned {time_response.status_code}")
            return []
        
        time_data = time_response.json()
        timetable = time_data.get('timetable', [])
        
        # Filter available slots
        available_slots = [
            slot['time'] for slot in timetable 
            if slot.get('availability') != 'SOLD_OUT'
        ]
        
        return available_slots
        
    except Exception as e:
        logger.error(f"   API check failed: {e}")
        return []


def _pick_best_slot(available_slots: list, target_time: str) -> str:
    """
    Pick the best available slot closest to target time
    
    Args:
        available_slots: List of available time slots (HH:MM)
        target_time: Preferred time (HH:MM)
    
    Returns:
        Best slot (HH:MM)
    """
    if not available_slots:
        return None
    
    if not target_time:
        # No preference, return first slot
        return available_slots[0]
    
    # Convert to minutes for comparison
    def time_to_mins(time_str):
        h, m = time_str.split(':')
        return int(h) * 60 + int(m)
    
    target_mins = time_to_mins(target_time)
    
    # Find closest slot
    best_slot = min(
        available_slots,
        key=lambda slot: abs(time_to_mins(slot) - target_mins)
    )
    
    return best_slot
