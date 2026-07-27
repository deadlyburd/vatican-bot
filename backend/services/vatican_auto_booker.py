"""
Vatican Auto Booker
===================
Complete automated booking system:
1. Monitors Vatican API for availability
2. Automatically books tickets with customer details
3. Updates Google Sheets with checkout link
"""

import logging
import asyncio
from datetime import datetime
from typing import Dict, Optional
from django.conf import settings
import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)


class VaticanAutoBooker:
    """Handles complete automated Vatican booking flow"""
    
    def __init__(self):
        self.sheets_client = None
        self._init_sheets()
    
    def _init_sheets(self):
        """Initialize Google Sheets client"""
        try:
            scopes = ['https://www.googleapis.com/auth/spreadsheets']
            creds = Credentials.from_service_account_file(
                settings.GOOGLE_SERVICE_ACCOUNT_FILE,
                scopes=scopes
            )
            self.sheets_client = gspread.authorize(creds)
            logger.info("✅ Google Sheets client initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Sheets: {e}")
    
    async def book_ticket_automated(
        self,
        task,  # VaticanTask model instance
        available_slot: str,  # HH:MM format
    ) -> Dict:
        """
        Complete automated booking flow
        
        Args:
            task: VaticanTask instance with booking details
            available_slot: Time slot to book (HH:MM)
        
        Returns:
            dict with success, epay_url, reference, error
        """
        from backend.monitors.playwright_checkout import checkout_full_ui
        from backend.models import BuyerProfile
        
        logger.info(f"🎫 Starting automated booking for {task.booking_id}")
        logger.info(f"   Date: {task.target_date.strftime('%d/%m/%Y')}")
        logger.info(f"   Time: {available_slot}")
        logger.info(f"   Visitors: {task.visitors}")
        logger.info(f"   Customer: {task.customer_name}")
        
        # Create or get buyer profile from task data
        profile = await self._create_buyer_profile(task)
        
        # Run Playwright checkout
        try:
            result = await checkout_full_ui(
                date=task.target_date.strftime('%d/%m/%Y'),
                slot_time=available_slot,
                visitors=task.visitors,
                profile=profile,
                timeout_s=180  # 3 minutes for Turnstile
            )
            
            if result.get('success'):
                logger.info(f"✅ Booking successful!")
                logger.info(f"   Reference: {result.get('reference')}")
                logger.info(f"   Epay URL: {result.get('epay_url')}")
                logger.info(f"   Total: €{result.get('total')}")
                
                # Update task status
                task.status = 'booked'
                task.booked_time = available_slot
                task.checkout_url = result.get('epay_url')
                task.reference_code = result.get('reference')
                task.save()
                
                # Update Google Sheets
                await self._update_sheets_with_booking(task, result)
                
                # Send Telegram notification
                await self._send_booking_notification(task, result)
                
                return result
            else:
                logger.error(f"❌ Booking failed: {result.get('error')}")
                task.status = 'failed'
                task.save()
                return result
                
        except Exception as e:
            logger.error(f"❌ Booking exception: {e}")
            task.status = 'failed'
            task.save()
            return {'success': False, 'error': str(e)}
    
    async def _create_buyer_profile(self, task):
        """Create BuyerProfile from task data"""
        from backend.models import BuyerProfile
        import json
        
        # Parse customer name
        name_parts = task.customer_name.strip().split()
        first_name = name_parts[0] if name_parts else 'Customer'
        last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else 'Name'
        
        # Create or get profile
        profile, created = await asyncio.to_thread(
            BuyerProfile.objects.get_or_create,
            email=task.customer_email,
            defaults={
                'first_name': first_name,
                'last_name': last_name,
                'phone': task.customer_phone or '+39 06 12345678',
                'city': 'ROMA',
                'country': 'IT',
                'birth_date': datetime(1990, 1, 1).date(),
                'gender': 'M',
                'language': 'it',
            }
        )
        
        # Create participant names for all visitors
        participants = []
        for i in range(task.visitors):
            participants.append({
                'first_name': first_name if i == 0 else f'{first_name}{i+1}',
                'last_name': last_name
            })
        
        profile.participants_json = json.dumps(participants)
        await asyncio.to_thread(profile.save)
        
        logger.info(f"   Profile: {profile.first_name} {profile.last_name} ({profile.email})")
        
        return profile
    
    async def _update_sheets_with_booking(self, task, result):
        """Update Google Sheets with booking confirmation"""
        if not self.sheets_client:
            logger.warning("⚠️ Google Sheets not initialized, skipping update")
            return
        
        try:
            sheet = await asyncio.to_thread(
                self.sheets_client.open_by_key,
                settings.GOOGLE_SHEET_ID
            )
            
            # Update Activity_Lines worksheet
            activity_ws = await asyncio.to_thread(sheet.worksheet, 'Activity_Lines')
            
            # Find the row with this booking ID
            all_values = await asyncio.to_thread(activity_ws.get_all_values)
            headers = all_values[0]
            
            # Find confirmationCode column
            conf_code_col = headers.index('confirmationCode') + 1 if 'confirmationCode' in headers else None
            
            if conf_code_col:
                # Find the row
                for row_idx, row in enumerate(all_values[1:], start=2):
                    if row[conf_code_col - 1] == task.booking_id:
                        # Add checkout URL and reference to notes column
                        notes_col = headers.index('notes') + 1 if 'notes' in headers else len(headers) + 1
                        
                        checkout_info = (
                            f"✅ BOOKED\n"
                            f"Time: {task.booked_time}\n"
                            f"Reference: {result.get('reference')}\n"
                            f"Checkout: {result.get('epay_url')}\n"
                            f"Total: €{result.get('total')}\n"
                            f"Booked: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        
                        await asyncio.to_thread(
                            activity_ws.update_cell,
                            row_idx,
                            notes_col,
                            checkout_info
                        )
                        
                        logger.info(f"✅ Updated Google Sheets row {row_idx}")
                        break
            
        except Exception as e:
            logger.error(f"❌ Failed to update Google Sheets: {e}")
    
    async def _send_booking_notification(self, task, result):
        """Send Telegram notification about successful booking"""
        try:
            from backend.services.telegram_service import send_telegram_message
            
            message = (
                f"🎉 <b>Vatican Booking Complete!</b>\n\n"
                f"📋 <b>Booking ID:</b> {task.booking_id}\n"
                f"📅 <b>Date:</b> {task.target_date.strftime('%d/%m/%Y')}\n"
                f"🕐 <b>Time:</b> {task.booked_time}\n"
                f"👥 <b>Visitors:</b> {task.visitors}\n"
                f"👤 <b>Customer:</b> {task.customer_name}\n"
                f"📧 <b>Email:</b> {task.customer_email}\n\n"
                f"💳 <b>Reference:</b> <code>{result.get('reference')}</code>\n"
                f"💰 <b>Total:</b> €{result.get('total')}\n\n"
                f"🔗 <b>Checkout URL:</b>\n"
                f"{result.get('epay_url')}\n\n"
                f"⚠️ <b>Action Required:</b> Complete payment within 15 minutes!"
            )
            
            await send_telegram_message(message)
            logger.info("✅ Telegram notification sent")
            
        except Exception as e:
            logger.error(f"❌ Failed to send Telegram notification: {e}")


# Singleton instance
_auto_booker = None

def get_auto_booker() -> VaticanAutoBooker:
    """Get or create auto booker instance"""
    global _auto_booker
    if _auto_booker is None:
        _auto_booker = VaticanAutoBooker()
    return _auto_booker
