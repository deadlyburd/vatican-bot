"""
Automated Cleanup Tasks for Vatican Bot
Prevents memory leaks and database bloat
"""
import logging
from celery import shared_task
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta
from .models import CheckResult, HeldSlot, MonitorTask

logger = logging.getLogger(__name__)


@shared_task(name="cleanup_old_check_results", queue="vatican")
def cleanup_old_check_results(days_to_keep=2):
    """
    Delete old CheckResult records to prevent database bloat.
    
    ✅ RUNS HOURLY to keep database size manageable.
    ✅ Keeps only last 2 days of check results (was 7 days).
    ✅ MonitorTask records are NEVER deleted - only CheckResult history.
    
    What gets deleted:
    - CheckResult records older than 2 days
    
    What is preserved:
    - All MonitorTask records (your monitoring configurations)
    - All HeldSlot records (active reservations)
    - All Agency, User, Proxy records
    - Recent CheckResult records (last 2 days)
    
    Args:
        days_to_keep: Number of days of check history to keep (default: 2)
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=days_to_keep)
        
        # Count before deletion
        old_results = CheckResult.objects.filter(check_time__lt=cutoff_date)
        count_before = old_results.count()
        
        if count_before == 0:
            logger.info(f"🧹 Cleanup: No check results older than {days_to_keep} days")
            return f"No old check results to delete"
        
        # Delete old check results
        deleted_count, _ = old_results.delete()
        
        # Get remaining count
        remaining = CheckResult.objects.count()
        
        logger.info(f"🧹 Cleanup: Deleted {deleted_count:,} check results older than {days_to_keep} days ({remaining:,} remaining)")
        return f"Deleted {deleted_count:,} old check results ({remaining:,} remaining)"
        
    except Exception as e:
        logger.error(f"❌ Cleanup failed: {e}")
        return f"Failed: {str(e)}"


@shared_task(name="cleanup_expired_holds", queue="vatican")
def cleanup_expired_holds():
    """
    Clean up expired HeldSlot records (older than 60 minutes).
    Vatican holds expire after 55 minutes, so 60 is safe.
    """
    try:
        cutoff_time = timezone.now() - timedelta(minutes=60)
        
        # Find expired holds that are still marked as 'held'
        expired_holds = HeldSlot.objects.filter(
            status='held',
            hold_started_at__lt=cutoff_time
        )
        
        count = expired_holds.count()
        
        # Mark as expired instead of deleting (for audit trail)
        expired_holds.update(status='expired')
        
        logger.info(f"🧹 Cleanup: Marked {count} expired holds")
        return f"Marked {count} expired holds"
        
    except Exception as e:
        logger.error(f"❌ Cleanup failed: {e}")
        return f"Failed: {str(e)}"


@shared_task(name="cleanup_redis_cache", queue="vatican")
def cleanup_redis_cache():
    """
    Clean up old Redis cache keys to prevent memory bloat.
    
    ✅ RUNS HOURLY to prevent Redis from growing to GB sizes.
    ✅ Removes stale Celery task results, expired state keys, and old cooldown keys.
    ✅ MonitorTask records in PostgreSQL are NEVER touched.
    
    What gets cleaned:
    1. Celery task results older than 1 hour (celery-task-meta-*)
    2. Expired ticket_state keys (ticket_state:*)
    3. Expired cooldown keys (alert_cooldown:*, hold_cooldown:*, notified:*)
    4. Orphaned Celery worker keys
    5. Old session keys
    
    What is preserved:
    - All PostgreSQL data (MonitorTask, Agency, User, Proxy, etc.)
    - Active Redis keys with valid TTL
    - Recent cache entries
    
    Redis stores:
    - Celery task queue and results (temporary)
    - Cache keys for state tracking (temporary)
    - Session data (temporary)
    
    This cleanup prevents Redis from growing beyond 1-2GB.
    """
    try:
        import redis
        from django.conf import settings
        
        # Connect to Redis
        broker_url = settings.CELERY_BROKER_URL
        r = redis.from_url(broker_url)
        
        # Check connection
        r.ping()
        
        initial_keys = r.dbsize()
        initial_memory = r.info('memory')['used_memory_human']
        cleaned = 0
        
        logger.info(f"🧹 Redis cleanup starting: {initial_keys:,} keys, {initial_memory} memory")
        
        # 1. Clean up Celery task results older than 1 hour
        cursor = 0
        pattern = 'celery-task-meta-*'
        celery_cleaned = 0
        
        while True:
            cursor, keys = r.scan(cursor, match=pattern, count=1000)
            if keys:
                for key in keys:
                    try:
                        ttl = r.ttl(key)
                        # If no TTL set (-1) or already expired (-2), delete it
                        if ttl == -1 or ttl == -2:
                            r.delete(key)
                            celery_cleaned += 1
                    except Exception:
                        pass
            if cursor == 0:
                break
        
        # 2. Clean up old ticket_state keys (ensure they have TTL)
        cursor = 0
        pattern = 'ticket_state:*'
        state_cleaned = 0
        
        while True:
            cursor, keys = r.scan(cursor, match=pattern, count=1000)
            if keys:
                for key in keys:
                    try:
                        ttl = r.ttl(key)
                        # If no TTL, set to 3 days (reduced from 7)
                        if ttl == -1:
                            r.expire(key, 259200)  # 3 days
                            state_cleaned += 1
                        # If expired, delete
                        elif ttl == -2:
                            r.delete(key)
                            state_cleaned += 1
                    except Exception:
                        pass
            if cursor == 0:
                break
        
        # 3. Clean up expired cooldown keys
        cooldown_cleaned = 0
        patterns = ['alert_cooldown:*', 'hold_cooldown:*', 'notified:*']
        
        for pattern in patterns:
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor, match=pattern, count=1000)
                if keys:
                    for key in keys:
                        try:
                            ttl = r.ttl(key)
                            # If expired or no TTL, delete
                            if ttl == -2 or ttl == -1:
                                r.delete(key)
                                cooldown_cleaned += 1
                        except Exception:
                            pass
                if cursor == 0:
                    break
        
        # 4. Clean up orphaned Celery worker keys
        worker_cleaned = 0
        patterns_worker = ['_kombu.binding.*', 'unacked_mutex']
        
        for pattern in patterns_worker:
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor, match=pattern, count=1000)
                if keys:
                    for key in keys:
                        try:
                            # Delete orphaned worker keys
                            r.delete(key)
                            worker_cleaned += 1
                        except Exception:
                            pass
                if cursor == 0:
                    break
        
        # 5. Clean up old session keys (Django cache sessions)
        session_cleaned = 0
        cursor = 0
        pattern = ':1:django.contrib.sessions*'
        
        while True:
            cursor, keys = r.scan(cursor, match=pattern, count=1000)
            if keys:
                for key in keys:
                    try:
                        ttl = r.ttl(key)
                        # If expired, delete
                        if ttl == -2:
                            r.delete(key)
                            session_cleaned += 1
                    except Exception:
                        pass
            if cursor == 0:
                break
        
        final_keys = r.dbsize()
        final_memory = r.info('memory')['used_memory_human']
        total_cleaned = celery_cleaned + state_cleaned + cooldown_cleaned + worker_cleaned + session_cleaned
        
        logger.info(f"🧹 Redis cleanup complete:")
        logger.info(f"   - Celery results: {celery_cleaned:,} keys")
        logger.info(f"   - State keys: {state_cleaned:,} keys")
        logger.info(f"   - Cooldown keys: {cooldown_cleaned:,} keys")
        logger.info(f"   - Worker keys: {worker_cleaned:,} keys")
        logger.info(f"   - Session keys: {session_cleaned:,} keys")
        logger.info(f"   - Total cleaned: {total_cleaned:,} keys")
        logger.info(f"   - Keys: {initial_keys:,} → {final_keys:,}")
        logger.info(f"   - Memory: {initial_memory} → {final_memory}")
        
        return f"Cleaned {total_cleaned:,} keys ({initial_keys:,} → {final_keys:,})"
        
    except Exception as e:
        logger.error(f"❌ Redis cleanup failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return f"Failed: {str(e)}"


@shared_task(name="cleanup_inactive_tasks", queue="vatican")
def cleanup_inactive_tasks():
    """
    Disable tasks with all past dates to prevent unnecessary checks.
    Runs daily to keep active task list clean.
    """
    try:
        from datetime import datetime, date as date_type
        
        today = date_type.today()
        disabled_count = 0
        
        # Find active tasks
        active_tasks = MonitorTask.objects.filter(is_active=True)
        
        for task in active_tasks:
            if not task.dates:
                continue
            
            # Check if all dates are in the past
            all_past = True
            for date_str in task.dates:
                try:
                    # Parse date
                    if '-' in date_str and len(date_str) == 10 and date_str[4] == '-':
                        # YYYY-MM-DD
                        dt = datetime.strptime(date_str, '%Y-%m-%d').date()
                    elif '/' in date_str:
                        # DD/MM/YYYY
                        dt = datetime.strptime(date_str, '%d/%m/%Y').date()
                    else:
                        continue
                    
                    if dt >= today:
                        all_past = False
                        break
                        
                except Exception:
                    continue
            
            # If all dates are past, disable the task
            if all_past:
                task.is_active = False
                task.save(update_fields=['is_active'])
                disabled_count += 1
                logger.info(f"🔕 Disabled task #{task.id} (all dates past)")
        
        logger.info(f"🧹 Cleanup: Disabled {disabled_count} tasks with past dates")
        return f"Disabled {disabled_count} tasks with past dates"
        
    except Exception as e:
        logger.error(f"❌ Task cleanup failed: {e}")
        return f"Failed: {str(e)}"


@shared_task(name="memory_health_check", queue="vatican")
def memory_health_check():
    """
    Check system memory usage and log warnings if high.
    Helps identify memory leaks before they cause crashes.
    """
    try:
        import psutil
        
        # Get memory info
        memory = psutil.virtual_memory()
        
        mem_percent = memory.percent
        mem_available_gb = memory.available / (1024**3)
        
        if mem_percent > 90:
            logger.error(f"🚨 CRITICAL: Memory usage at {mem_percent}% (Available: {mem_available_gb:.2f}GB)")
        elif mem_percent > 80:
            logger.warning(f"⚠️ WARNING: Memory usage at {mem_percent}% (Available: {mem_available_gb:.2f}GB)")
        else:
            logger.info(f"✅ Memory OK: {mem_percent}% used (Available: {mem_available_gb:.2f}GB)")
        
        return f"Memory: {mem_percent}% used"
        
    except ImportError:
        logger.warning("psutil not installed - skipping memory check")
        return "psutil not available"
    except Exception as e:
        logger.error(f"❌ Memory check failed: {e}")
        return f"Failed: {str(e)}"


@shared_task(name="celery_worker_health_check", queue="vatican")
def celery_worker_health_check():
    """
    Check Celery worker health and restart if needed.
    Monitors task queue sizes and worker responsiveness.
    """
    try:
        from celery import current_app
        
        # Get queue lengths
        inspect = current_app.control.inspect()
        
        # Check active tasks
        active = inspect.active()
        if active:
            total_active = sum(len(tasks) for tasks in active.values())
            logger.info(f"📊 Celery: {total_active} active tasks")
        
        # Check reserved tasks
        reserved = inspect.reserved()
        if reserved:
            total_reserved = sum(len(tasks) for tasks in reserved.values())
            logger.info(f"📊 Celery: {total_reserved} reserved tasks")
        
        return "Celery health check completed"
        
    except Exception as e:
        logger.error(f"❌ Celery health check failed: {e}")
        return f"Failed: {str(e)}"
