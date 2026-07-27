"""
Reacquisition Agent - 24-Hour Expiry Workaround
================================================

Handles automatic re-acquisition of slots approaching Vatican's 24-hour expiry limit.
"""

import os
import time
import logging
import json
from datetime import datetime, timedelta

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

from . import AIAgentBase
from monitors.models import HeldSlot, ReacquisitionQueue, MonitorTask
from monitors.tasks_search_api import search_specific_date
from monitors.tasks_hold import auto_hold_slot

logger = logging.getLogger(__name__)

class ReacquisitionAgent(AIAgentBase):
    """AI agent for automatic slot re-acquisition"""
    
    def __init__(self):
        super().__init__("ReacquisitionAgent")
        self.check_interval = int(os.getenv('REACQUISITION_INTERVAL', 60))  # seconds
        self.expiry_threshold = int(os.getenv('EXPIRY_THRESHOLD', 23))  # hours
        self.max_reacquisition_attempts = int(os.getenv('MAX_REACQUISITION_ATTEMPTS', 5))
        
    def find_expiring_holds(self):
        """Find holds approaching 24-hour expiry"""
        try:
            # Find holds that will expire in the next 1-2 hours
            threshold_time = timezone.now() - timedelta(hours=self.expiry_threshold)
            
            expiring_holds = HeldSlot.objects.filter(
                status='held',
                hold_started_at__lte=threshold_time,
                reacquisition_attempts__lt=self.max_reacquisition_attempts
            )
            
            logger.info(f"⏰ Found {expiring_holds.count()} holds approaching 24-hour expiry")
            
            for hold in expiring_holds:
                self.add_to_reacquisition_queue(hold)
                
        except Exception as e:
            logger.error(f"Error finding expiring holds: {e}")
    
    def add_to_reacquisition_queue(self, hold):
        """Add expiring hold to reacquisition queue"""
        try:
            # Check if already in queue
            existing = ReacquisitionQueue.objects.filter(
                original_hold_id=hold.id,
                status__in=['pending', 'processing']
            ).first()
            
            if existing:
                logger.debug(f"⏭️ Hold #{hold.id} already in reacquisition queue")
                return
            
            # Create reacquisition task
            reacq_task = ReacquisitionQueue.objects.create(
                original_hold_id=hold.id,
                date=hold.date,
                slot_time=hold.slot_time,
                visitors=hold.visitors,
                task_id=hold.task.id,
                priority='high',
                status='pending',
                parameters=json.dumps({
                    'date': hold.date,
                    'time': hold.slot_time,
                    'visitors': hold.visitors,
                    'task_id': hold.task.id,
                    'original_hold_id': hold.id
                })
            )
            
            logger.info(f"📋 Added hold #{hold.id} to reacquisition queue (ID: {reacq_task.id})")
            
            # Increment attempt counter
            hold.reacquisition_attempts = (hold.reacquisition_attempts or 0) + 1
            hold.save(update_fields=['reacquisition_attempts'])
            
        except Exception as e:
            logger.error(f"Error adding to reacquisition queue: {e}")
    
    def process_reacquisition_queue(self):
        """Process pending reacquisition requests"""
        try:
            pending_tasks = ReacquisitionQueue.objects.filter(
                status='pending',
                created_at__gte=timezone.now() - timedelta(hours=2)  # Only recent tasks
            )
            
            logger.info(f"🔄 Processing {pending_tasks.count()} reacquisition tasks")
            
            for task in pending_tasks:
                try:
                    task.status = 'processing'
                    task.save(update_fields=['status'])
                    
                    success = self.attempt_reacquisition(task)
                    
                    if success:
                        task.status = 'completed'
                        task.completed_at = timezone.now()
                        logger.info(f"✅ Reacquisition completed for task #{task.id}")
                    else:
                        task.status = 'failed'
                        task.attempts += 1
                        logger.warning(f"❌ Reacquisition failed for task #{task.id} (attempt {task.attempts})")
                    
                    task.save()
                    
                except Exception as e:
                    logger.error(f"Error processing reacquisition task #{task.id}: {e}")
                    task.status = 'error'
                    task.save()
                    
        except Exception as e:
            logger.error(f"Error processing reacquisition queue: {e}")
    
    def attempt_reacquisition(self, task):
        """Attempt to re-acquire a specific slot"""
        try:
            params = json.loads(task.parameters)
            date_str = params['date']
            time_str = params['time']
            visitors = params['visitors']
            task_id = params['task_id']
            
            logger.info(f"🎯 Attempting reacquisition: {date_str} {time_str} for {visitors} visitors")
            
            # Search for the specific slot
            search_result = search_specific_date(
                date_str=date_str,
                time_str=time_str,
                visitors=visitors
            )
            
            if not search_result or not search_result.get('available', False):
                logger.info(f"⏭️ Slot not available for reacquisition: {date_str} {time_str}")
                return False
            
            # Extract slot information
            slot_info = search_result.get('slots', [{}])[0]
            slot_id = slot_info.get('id')
            
            if not slot_id:
                logger.error("No slot ID found in search results")
                return False
            
            # Get the monitor task
            try:
                monitor_task = MonitorTask.objects.get(id=task_id)
            except MonitorTask.DoesNotExist:
                logger.error(f"Monitor task {task_id} not found")
                return False
            
            # Attempt to re-hold the slot
            held_slot = auto_hold_slot(
                task=monitor_task,
                date=date_str,
                slot_id=slot_id,
                slot_time=time_str,
                ticket_id=slot_info.get('ticket_id', 60),
                ticket_name=slot_info.get('name', 'Biglietto Intero'),
                visitors=visitors
            )
            
            if held_slot and held_slot.status == 'held':
                logger.info(f"✅ Successfully re-acquired slot! New Hold ID: {held_slot.id}")
                
                # Update task with new hold reference
                task.new_hold_id = held_slot.id
                
                # Send notification
                self.send_reacquisition_success_notification(task, held_slot)
                return True
            
            logger.warning("❌ Reacquisition attempt failed")
            return False
            
        except Exception as e:
            logger.error(f"Error in reacquisition attempt: {e}")
            return False
    
    def send_reacquisition_success_notification(self, task, new_hold):
        """Send success notification for reacquisition"""
        try:
            from monitors.notification_utils import send_telegram_message
            
            message = f"🔄 *REACQUISITION SUCCESS!* 🔄\n" \
                     f"✅ Hold re-acquired after 24-hour expiry\n" \
                     f"📅 Date: {new_hold.date}\n" \
                     f"⏰ Time: {new_hold.slot_time}\n" \
                     f"👥 Visitors: {new_hold.visitors}\n" \
                     f"🆔 New Hold ID: `{new_hold.id}`\n\n" \
                     f"The slot has been successfully re-held for another 24 hours."
            
            # Send to admin channel
            admin_chat_id = os.getenv('ADMIN_TELEGRAM_IDS')
            if admin_chat_id:
                send_telegram_message(admin_chat_id, message)
                
        except Exception as e:
            logger.error(f"Error sending reacquisition notification: {e}")
    
    def cleanup_old_holds(self):
        """Clean up expired holds from the database"""
        try:
            # Find holds that expired more than 2 hours ago
            expiry_time = timezone.now() - timedelta(hours=26)
            
            expired_holds = HeldSlot.objects.filter(
                status='held',
                hold_started_at__lte=expiry_time
            )
            
            if expired_holds.exists():
                logger.info(f"🧹 Cleaning up {expired_holds.count()} expired holds")
                
                for hold in expired_holds:
                    hold.status = 'expired'
                    hold.expired_at = timezone.now()
                    hold.save(update_fields=['status', 'expired_at'])
                    
        except Exception as e:
            logger.error(f"Error cleaning up old holds: {e}")
    
    def run(self):
        """Main reacquisition processing loop"""
        self.log_start()
        
        try:
            # 1. Find holds approaching expiry
            self.find_expiring_holds()
            
            # 2. Process reacquisition queue
            self.process_reacquisition_queue()
            
            # 3. Clean up expired holds
            self.cleanup_old_holds()
            
            self.log_success()
            
        except Exception as e:
            if not self.log_failure(e):
                # Critical failure - should restart
                raise

def main():
    """Main entry point for the reacquisition agent"""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    
    agent = ReacquisitionAgent()
    
    logger.info("🚀 Starting Reacquisition Agent (24-Hour Expiry Workaround)")
    logger.info(f"⏰ Check interval: {agent.check_interval}s")
    logger.info(f"⏳ Expiry threshold: {agent.expiry_threshold}h")
    
    # Continuous processing loop
    while True:
        try:
            agent.run()
            time.sleep(agent.check_interval)
            
        except KeyboardInterrupt:
            logger.info("🛑 Reacquisition Agent stopped by user")
            break
        except Exception as e:
            logger.error(f"❌ Critical error in reacquisition loop: {e}")
            time.sleep(30)  # Wait before retrying

if __name__ == "__main__":
    main()