import logging
from django.utils import timezone
from .models import VaticanTask, HeldSlot
from backend.services.ai_evaluator import get_evaluator
import asyncio
from asgiref.sync import async_to_sync

from backend.services.customer_care import get_customer_care

logger = logging.getLogger(__name__)

def run_orchestration():
    """
    Main entry point for the Orchestrator (called by Celery Beat every minute).
    """
    logger.info("🎯 Orchestrator: Starting cycle...")
    
    # 1. Handle 'new' tasks -> 'checking'
    new_tasks = VaticanTask.objects.filter(status='new')
    for task in new_tasks:
        orchestrate_new_task(task)
        
    # 2. Handle 'checking' tasks
    checking_tasks = VaticanTask.objects.filter(status='checking')
    for task in checking_tasks:
        orchestrate_checking_task(task)
        
    # 3. Handle 'awaiting_info' tasks (Periodic reminders)
    # (Optional: can add logic to resend if no reply after X hours)
    
    # 4. Handle 'ready' tasks -> Start monitoring
    ready_tasks = VaticanTask.objects.filter(status='ready')
    for task in ready_tasks:
        orchestrate_ready_task(task)
    
    logger.info("🎯 Orchestrator: Cycle complete.")

def orchestrate_new_task(task):
    """Transitions a new task to checking."""
    logger.info(f"Task #{task.id}: new -> checking")
    task.status = 'checking'
    task.save()

def orchestrate_checking_task(task):
    """Uses AI to evaluate data completeness."""
    evaluator = get_evaluator()
    
    # Run async evaluator in sync context
    is_complete, summary, missing = async_to_sync(evaluator.validate_task)(task)
    
    if is_complete:
        logger.info(f"Task #{task.id}: checking -> ready (AI confirmed)")
        task.status = 'ready'
        task.missing_info = None
    else:
        logger.info(f"Task #{task.id}: checking -> awaiting_info (Missing: {missing})")
        task.status = 'awaiting_info'
        task.missing_info = summary
        
        # Log finding
        log_entry = {
            "timestamp": timezone.now().isoformat(),
            "action": "ai_validation_failed",
            "missing": missing,
            "summary": summary
        }
        if not task.contact_log:
            task.contact_log = []
        task.contact_log.append(log_entry)
        task.save()
        
        # TRIGGER CUSTOMER CARE
        care = get_customer_care()
        async_to_sync(care.send_missing_info_request)(task)
        
    task.save()

def orchestrate_ready_task(task):
    """Move ready tasks to monitoring."""
    logger.info(f"Task #{task.id}: ready -> monitoring")
    task.status = 'monitoring'
    task.save()
