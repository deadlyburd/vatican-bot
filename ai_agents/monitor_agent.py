"""
AI Monitor Agent - Continuous Vatican API Monitoring
====================================================

Continuously monitors Vatican ticket availability and holds slots automatically.
"""

import os
import time
import logging
from datetime import datetime, timedelta
from django.utils import timezone

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

from . import AIAgentBase
from monitors.models import MonitorTask, HeldSlot
from monitors.tasks_search_api import search_date_range
from monitors.tasks_hold import auto_hold_slot
from monitors.hold_manager import keepalive_slot

logger = logging.getLogger(__name__)

class MonitorAgent(AIAgentBase):
    """AI agent for continuous Vatican ticket monitoring"""
    
    def __init__(self):
        super().__init__("MonitorAgent")
        self.monitor_interval = int(os.getenv('MONITOR_INTERVAL', 30))  # seconds
        self.max_concurrent_holds = int(os.getenv('MAX_CONCURRENT_HOLDS', 10))
        
    def should_run(self):
        """Run continuously with configured interval"""
        if self.last_run:
            time_since_last = (datetime.now() - self.last_run).total_seconds()
            return time_since_last >= self.monitor_interval
        return True
    
    def check_existing_holds(self):
        """Check and maintain existing held slots"""
        try:
            active_holds = HeldSlot.objects.filter(status='held')
            logger.info(f"🔍 Checking {active_holds.count()} active holds")
            
            for hold in active_holds:
                if not keepalive_slot(hold):
                    logger.warning(f"⚠️ Hold #{hold.id} failed keepalive - may need refresh")
                    
        except Exception as e:
            logger.error(f"Error checking existing holds: {e}")
    
    def scan_for_availability(self):
        """Scan for new ticket availability"""
        try:
            # Get all active monitor tasks
            tasks = MonitorTask.objects.filter(is_active=True)
            logger.info(f"📊 Scanning {tasks.count()} active monitor tasks")
            
            for task in tasks:
                try:
                    # Scan next 3 months for this task
                    start_date = timezone.now().date()
                    end_date = start_date + timedelta(days=90)
                    
                    logger.info(f"🔎 Scanning {task.site} from {start_date} to {end_date}")
                    
                    # Use existing search functionality
                    results = search_date_range(
                        task_id=task.id,
                        start_date=start_date.strftime('%Y-%m-%d'),
                        end_date=end_date.strftime('%Y-%m-%d'),
                        visitors=task.visitors or 2
                    )
                    
                    if results and 'available_dates' in results:
                        available_count = len(results['available_dates'])
                        logger.info(f"🎯 Found {available_count} available dates for {task.site}")
                        
                        # Auto-hold if configured for this task
                        if task.tier != 'notify' and available_count > 0:
                            self.auto_hold_available_slots(task, results['available_dates'])
                            
                except Exception as e:
                    logger.error(f"Error scanning task {task.id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in availability scan: {e}")
    
    def auto_hold_available_slots(self, task, available_dates):
        """Automatically hold available slots based on task configuration"""
        try:
            current_holds = HeldSlot.objects.filter(task=task, status='held').count()
            
            if current_holds >= self.max_concurrent_holds:
                logger.info(f"⏭️ Task {task.id} has {current_holds} holds (max: {self.max_concurrent_holds}) - skipping")
                return
            
            # For each available date, try to hold a slot
            for date_info in available_dates[:3]:  # Limit to top 3 dates
                try:
                    # Extract slot information (adjust based on your API response format)
                    date_str = date_info.get('date')
                    slot_id = date_info.get('slot_id')
                    slot_time = date_info.get('time')
                    ticket_id = date_info.get('ticket_id', 60)  # Default to Biglietto Intero
                    
                    if all([date_str, slot_id, slot_time]):
                        logger.info(f"🔄 Attempting to hold {date_str} {slot_time} for task {task.id}")
                        
                        # Use existing auto_hold_slot task
                        auto_hold_slot.delay(
                            task_id=task.id,
                            date=date_str,
                            slot_id=slot_id,
                            slot_time=slot_time,
                            ticket_id=ticket_id,
                            ticket_name=date_info.get('ticket_name', 'Biglietto Intero'),
                            visitors=task.visitors or 2
                        )
                        
                except Exception as e:
                    logger.error(f"Error holding slot for date {date_str}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in auto-hold process: {e}")
    
    def run(self):
        """Main monitoring loop"""
        self.log_start()
        
        try:
            # 1. Check and maintain existing holds
            self.check_existing_holds()
            
            # 2. Scan for new availability
            self.scan_for_availability()
            
            self.log_success()
            
        except Exception as e:
            if not self.log_failure(e):
                # Critical failure - should restart
                raise

def main():
    """Main entry point for the monitor agent"""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    
    agent = MonitorAgent()
    
    logger.info("🚀 Starting AI Monitor Agent (Continuous Mode)")
    logger.info(f"📊 Monitor Interval: {agent.monitor_interval}s")
    logger.info(f"🔒 Max Concurrent Holds: {agent.max_concurrent_holds}")
    
    # Continuous monitoring loop
    while True:
        try:
            if agent.should_run():
                agent.run()
            
            # Sleep until next cycle
            time.sleep(5)  # Check every 5 seconds if should_run
            
        except KeyboardInterrupt:
            logger.info("🛑 Monitor Agent stopped by user")
            break
        except Exception as e:
            logger.error(f"❌ Critical error in monitor loop: {e}")
            time.sleep(30)  # Wait before retrying

if __name__ == "__main__":
    main()