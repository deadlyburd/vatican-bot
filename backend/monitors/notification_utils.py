"""
Enhanced Telegram Notification Utilities
=======================================
Provides improved notification formatting with:
- Preferred time highlighting
- Direct booking links
- Better visual formatting
"""

import logging
import os
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def escape_markdown(text: str) -> str:
    """Escape special characters for Telegram Markdown"""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def format_vatican_notification(
    date: str,
    ticket_name: str,
    ticket_id: str,
    slots: List[Dict],
    preferred_times: Optional[List[str]] = None,
    language: Optional[str] = None,
    visitors: int = 1,
    check_method: str = "browser"
) -> str:
    """
    Format an enhanced Telegram notification for Vatican tickets.
    
    Args:
        date: Date in DD/MM/YYYY format
        ticket_name: Human-readable ticket name
        ticket_id: Vatican ticket ID
        slots: List of available slots (dicts with 'time' and optionally 'availability')
        preferred_times: List of user's preferred times (e.g., ['08:00', '10:00'])
        language: Language code (ENG/ITA/etc.)
        visitors: Number of visitors
        check_method: How the check was performed (browser/headless/hybrid)
    
    Returns:
        Formatted message string
    """
    # Normalize preferred times for comparison
    preferred_times = preferred_times or []
    preferred_set = set()
    for pt in preferred_times:
        # Handle various formats: "8:00", "08:00", "8", "08"
        preferred_set.add(pt.strip())
        # Add normalized versions
        if ':' in pt:
            parts = pt.split(':')
            preferred_set.add(f"{int(parts[0]):02d}:{parts[1]}")  # 8:00 -> 08:00
            preferred_set.add(str(int(parts[0])))  # 8:00 -> 8
        else:
            preferred_set.add(f"{int(pt):02d}:00")  # 8 -> 08:00
            preferred_set.add(f"{int(pt)}")  # 8 -> 8
    
    # Build direct booking link
    # Convert date to timestamp for URL
    try:
        if "/" in date:
            day, month, year = date.split('/')
        elif "-" in date:
            year, month, day = date.split('-')
        else:
            day, month, year = date, "01", "2026"
        
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        dt_obj = datetime(int(year), int(month), int(day))
        rome = ZoneInfo("Europe/Rome")
        midnight = dt_obj.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=rome)
        ts = int(midnight.timestamp() * 1000)
        
        # Determine slug based on ticket type
        is_guided = "Guidat" in ticket_name or "Guided" in ticket_name
        slug = "MV-Visite-Guidate" if is_guided else "MV-Biglietti"
        
        booking_link = f"https://tickets.museivaticani.va/home/fromtag/{visitors}/{ts}/{slug}/1"
    except Exception as e:
        logger.warning(f"Could not generate booking link: {e}")
        booking_link = "https://tickets.museivaticani.va/home"
    
    # Build message - Plain text to avoid Markdown parsing issues
    lang_info = f" ({language})" if language else ""
    
    # Get current time for "Checked at" info
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    rome_tz = ZoneInfo('Europe/Rome')
    now = datetime.now(rome_tz)
    checked_at = now.strftime("%H:%M:%S")
    
    message = f"🎉 TICKETS JUST OPENED!\n\n"
    message += f"━━━━━━━━━━━━━━━━━━━━━━\n"
    message += f"📅 DATE: {date}\n"
    message += f"🎫 TICKET: {ticket_name}{lang_info}\n"
    message += f"👥 VISITORS: {visitors}\n"
    message += f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
    message += f"⏰ Checked at: {checked_at} Rome time\n"
    message += f"🔍 Method: {check_method}\n\n"
    
    # Categorize slots
    preferred_slots = []
    other_slots = []
    
    for slot in slots:
        time_str = slot.get('time', slot) if isinstance(slot, dict) else slot
        # Normalize time for comparison
        time_normalized = time_str.strip()
        
        is_preferred = False
        if preferred_set:
            # Check if this time matches any preferred time
            if time_normalized in preferred_set:
                is_preferred = True
            elif ':' in time_normalized:
                hour = time_normalized.split(':')[0]
                if hour in preferred_set or str(int(hour)) in preferred_set:
                    is_preferred = True
        
        if is_preferred:
            preferred_slots.append(time_str)
        else:
            other_slots.append(time_str)
    
    # Add preferred slots first (highlighted)
    if preferred_slots:
        message += f"⭐ YOUR PREFERRED TIMES ({len(preferred_slots)}):\n"
        for slot in preferred_slots:
            message += f"   ⭐ {slot}\n"
        message += "\n"
    
    # Add ALL other available slots (no limit)
    if other_slots:
        message += f"🕐 {'Other ' if preferred_slots else ''}Available Times ({len(other_slots)}):\n"
        for slot in other_slots:
            message += f"   • {slot}\n"
        message += "\n"
    
    # Show total count
    message += f"📊 Total Available Slots: {len(slots)}\n\n"
    
    # Add booking link with emphasis
    message += f"━━━━━━━━━━━━━━━━━━━━━━\n"
    message += f"🔗 BOOK NOW:\n"
    message += f"{booking_link}\n"
    message += f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
    message += f"⚡ Act fast - tickets sell quickly!"
    
    return message


def send_telegram_signal(chat_id: str, message: str) -> bool:
    """
    Send a Telegram message with HTML/Markdown formatting.
    Now checks if group is approved before sending.
    
    Args:
        chat_id: Telegram chat ID
        message: Message text (can include Markdown)
    
    Returns:
        True if sent successfully, False otherwise
    """
    import requests
    from monitors.models import TelegramGroup

    # Check if this is a group and if it's approved
    try:
        group = TelegramGroup.objects.filter(chat_id=str(chat_id)).first()

        if group:
            if not group.is_approved():
                logger.warning(f"⏭️ Skipping notification to unapproved group: {chat_id} (status: {group.status})")
                return False

            if not group.notification_enabled:
                logger.info(f"🔕 Notifications disabled for group: {chat_id}")
                return False
    except Exception as e:
        logger.error(f"❌ Error checking group approval: {e}")
        # Continue anyway for backward compatibility with direct chat_ids
    
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        logger.error("❌ No TELEGRAM_BOT_TOKEN configured")
        return False
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    
    try:
        payload = {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": False
        }
        
        response = requests.post(
            url,
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info(f"✅ Telegram signal sent to {chat_id}")
            
            # Update last_activity for the group
            if group:
                from django.utils import timezone
                group.last_activity = timezone.now()
                group.save(update_fields=['last_activity'])
            
            return True
        else:
            logger.error(f"❌ Telegram API error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Failed to send Telegram signal: {e}")
        return False
