"""
AI Sniper Agent - On-Demand Ticket Acquisition
==============================================

Handles immediate ticket sniping requests via Telegram commands.
"""

import os
import time
import logging
import json
from datetime import datetime

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

from . import AIAgentBase
from monitors.models import MonitorTask, HeldSlot, SnipeRequest
from monitors.tasks_search_api import search_specific_date
from monitors.tasks_hold import auto_hold_slot
from monitors.hold_manager import hold_slot

logger = logging.getLogger(__name__)

class SniperAgent(AIAgentBase):
    """AI agent for on-demand ticket sniping"""
    
    def __init__(self):
        super().__init__("SniperAgent")
        self.sniper_timeout = int(os.getenv('SNIPER_TIMEOUT', 300))  # 5 minutes
        self.active_requests = {}
        
    def process_snipe_requests(self):
        """Process pending snipe requests from database"""
        try:
            # Get pending snipe requests (not processed, not expired)
            pending_requests = SnipeRequest.objects.filter(
                status='pending',
                created_at__gte=datetime.now() - timedelta(seconds=self.sniper_timeout)
            )
            
            logger.info(f"🎯 Processing {pending_requests.count()} pending snipe requests")
            
            for request in pending_requests:
                try:
                    # Parse request parameters
                    params = json.loads(request.parameters)
                    
                    logger.info(f"🔫 Processing snipe request #{request.id}: {params}")
                    
                    # Attempt to fulfill the request
                    success = self.attempt_snipe(request, params)
                    
                    if success:
                        request.status = 'completed'
                        request.completed_at = datetime.now()
                        logger.info(f"✅ Snipe request #{request.id} completed successfully")
                    else:
                        request.status = 'failed'
                        request.attempts += 1
                        logger.warning(f"❌ Snipe request #{request.id} failed (attempt {request.attempts})")
                    
                    request.save()
                    
                except Exception as e:
                    logger.error(f"Error processing snipe request #{request.id}: {e}")
                    request.status = 'error'
                    request.save()
                    
        except Exception as e:
            logger.error(f"Error processing snipe requests: {e}")
    
    def attempt_snipe(self, request, params):
        """Attempt to snipe a specific ticket"""
        try:
            # Extract parameters
            date_str = params.get('date')
            time_str = params.get('time')
            visitors = params.get('visitors', 2)
            task_id = params.get('task_id')
            
            if not all([date_str, time_str]):
                logger.error("Missing required parameters for snipe")
                return False
            
            # Get or create monitor task for sniping
            if task_id:
                try:
                    task = MonitorTask.objects.get(id=task_id)
                except MonitorTask.DoesNotExist:
                    logger.error(f"Task {task_id} not found for snipe")
                    return False
            else:
                # Create temporary task for sniping
                task = MonitorTask.objects.create(
                    name=f"Snipe-{date_str}-{time_str}",
                    site='vatican',
                    tier='snipe',
                    visitors=visitors,
                    is_active=True,
                    agency_id=1  # Default agency
                )
            
            # Search for specific date and time
            search_result = search_specific_date(
                date_str=date_str,
                time_str=time_str,
                visitors=visitors
            )
            
            if not search_result or 'available' not in search_result or not search_result['available']:
                logger.info(f"⏭️ No availability for {date_str} {time_str}")
                return False
            
            # Extract slot information
            slot_info = search_result.get('slots', [{}])[0]
            slot_id = slot_info.get('id')
            ticket_id = slot_info.get('ticket_id', 60)
            
            if not slot_id:
                logger.error("No slot ID found in search results")
                return False
            
            logger.info(f"🎯 Attempting to snipe slot {slot_id} on {date_str} {time_str}")
            
            # Direct hold attempt (bypass queue for immediate action)
            held_slot = hold_slot(
                task=task,
                date=date_str,
                slot_id=slot_id,
                slot_time=time_str,
                ticket_id=ticket_id,
                ticket_name=slot_info.get('name', 'Biglietto Intero'),
                visitors=visitors,
                proxy_str=None  # Use default proxy
            )
            
            if held_slot and held_slot.status == 'held':
                logger.info(f"✅ Successfully sniped slot! Hold ID: {held_slot.id}")
                
                # Store hold reference in request
                request.hold_id = held_slot.id
                
                # Send immediate notification
                self.send_snipe_success_notification(request, held_slot)
                return True
            
            logger.warning("❌ Snipe attempt failed - slot not held")
            return False
            
        except Exception as e:
            logger.error(f"Error in snipe attempt: {e}")
            return False
    
    def send_snipe_success_notification(self, request, held_slot):
        """Send success notification for successful snipe"""
        try:
            from monitors.notification_utils import send_telegram_message
            
            message = f"🎯 *SNIPE SUCCESS!* 🎯\n" \
                     f"✅ Hold ID: `{held_slot.id}`\n" \
                     f"📅 Date: {held_slot.date}\n" \
                     f"⏰ Time: {held_slot.slot_time}\n" \
                     f"👥 Visitors: {held_slot.visitors}\n" \
                     f"💶 Price: €{held_slot.total_price}\n\n" \
                     f"The slot is now held for 24 hours. Use `/checkout {held_slot.id}` to generate payment."
            
            # Send to requester if available
            if request.requester_id:
                send_telegram_message(request.requester_id, message)
            
            # Also send to admin channel
            admin_chat_id = os.getenv('ADMIN_TELEGRAM_IDS')
            if admin_chat_id:
                send_telegram_message(admin_chat_id, f"🎯 Snipe completed: {message}")
                
        except Exception as e:
            logger.error(f"Error sending snipe notification: {e}")
    
    def run(self):
        """Main sniper processing loop"""
        self.log_start()
        
        try:
            # Process any pending snipe requests
            self.process_snipe_requests()
            
            self.log_success()
            
        except Exception as e:
            if not self.log_failure(e):
                # Critical failure - should restart
                raise

def main():
    """Main entry point for the sniper agent"""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    
    agent = SniperAgent()
    
    logger.info("🚀 Starting AI Sniper Agent (On-Demand Mode)")
    logger.info(f"⏰ Sniper Timeout: {agent.sniper_timeout}s")
    
    # Continuous processing loop
    while True:
        try:
            agent.run()
            time.sleep(10)  # Check for new requests every 10 seconds
            
        except KeyboardInterrupt:
            logger.info("🛑 Sniper Agent stopped by user")
            break
        except Exception as e:
            logger.error(f"❌ Critical error in sniper loop: {e}")
            time.sleep(30)  # Wait before retrying

if __name__ == "__main__":
    main()