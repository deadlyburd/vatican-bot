#!/usr/bin/env python3
"""
REDIS BLOAT CLEANUP - Run inside Docker container
==================================================
Cleans up existing Redis bloat (220k+ keys)

Usage:
    docker-compose exec backend python fix_redis_bloat.py
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

import redis
from django.conf import settings
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def main():
    """Clean up Redis bloat"""
    logger.info("="*80)
    logger.info("REDIS CLEANUP - Removing bloat")
    logger.info("="*80)
    
    try:
        # Connect to Redis
        broker_url = settings.CELERY_BROKER_URL
        logger.info(f"Connecting to Redis: {broker_url}")
        r = redis.from_url(broker_url)
        
        # Check connection
        r.ping()
        logger.info("✅ Connected to Redis")
        
        # Get initial stats
        initial_keys = r.dbsize()
        initial_memory = r.info('memory')['used_memory_human']
        
        logger.info(f"\nInitial state:")
        logger.info(f"  Keys: {initial_keys:,}")
        logger.info(f"  Memory: {initial_memory}")
        
        if initial_keys < 10000:
            logger.info("\n✅ Redis is already clean (< 10k keys)")
            return True
        
        logger.info(f"\n⚠️ Redis has {initial_keys:,} keys - cleaning up...")
        
        # Clean up Celery task results (the main culprit)
        logger.info("\n1. Cleaning Celery task results...")
        deleted_celery = 0
        cursor = 0
        pattern = 'celery-task-meta-*'
        
        while True:
            cursor, keys = r.scan(cursor, match=pattern, count=1000)
            if keys:
                deleted_celery += r.delete(*keys)
                if deleted_celery % 10000 == 0:
                    logger.info(f"   Deleted {deleted_celery:,} task results...")
            if cursor == 0:
                break
        
        logger.info(f"✅ Deleted {deleted_celery:,} Celery task results")
        
        # Clean up old ticket state keys
        logger.info("\n2. Setting TTL on ticket state keys...")
        deleted_state = 0
        cursor = 0
        pattern = 'ticket_state:*'
        
        while True:
            cursor, keys = r.scan(cursor, match=pattern, count=1000)
            if keys:
                for key in keys:
                    try:
                        ttl = r.ttl(key)
                        if ttl == -1:  # No expiration
                            r.expire(key, 604800)  # 7 days
                            deleted_state += 1
                    except Exception:
                        pass
            if cursor == 0:
                break
        
        logger.info(f"✅ Set TTL on {deleted_state:,} ticket state keys")
        
        # Clean up old cooldown keys
        logger.info("\n3. Cleaning old cooldown keys...")
        deleted_cooldown = 0
        patterns = ['alert_cooldown:*', 'hold_cooldown:*', 'notified:*']
        
        for pattern in patterns:
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor, match=pattern, count=1000)
                if keys:
                    for key in keys:
                        try:
                            ttl = r.ttl(key)
                            if ttl == -2 or ttl == -1:
                                r.delete(key)
                                deleted_cooldown += 1
                        except Exception:
                            pass
                if cursor == 0:
                    break
        
        logger.info(f"✅ Deleted {deleted_cooldown:,} old cooldown keys")
        
        # Get final stats
        final_keys = r.dbsize()
        final_memory = r.info('memory')['used_memory_human']
        
        logger.info("\n" + "="*80)
        logger.info("CLEANUP SUMMARY")
        logger.info("="*80)
        logger.info(f"\nDeleted:")
        logger.info(f"  Celery results: {deleted_celery:,}")
        logger.info(f"  State keys (TTL set): {deleted_state:,}")
        logger.info(f"  Cooldown keys: {deleted_cooldown:,}")
        logger.info(f"  Total: {deleted_celery + deleted_state + deleted_cooldown:,}")
        
        logger.info(f"\nFinal state:")
        logger.info(f"  Keys: {final_keys:,} (was {initial_keys:,})")
        logger.info(f"  Memory: {final_memory} (was {initial_memory})")
        
        reduction = initial_keys - final_keys
        reduction_pct = (reduction / initial_keys * 100) if initial_keys > 0 else 0
        logger.info(f"  Reduction: {reduction:,} keys ({reduction_pct:.1f}%)")
        
        logger.info("\n" + "="*80)
        logger.info("✅ CLEANUP COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        logger.info("\n⚠️ NEXT STEP: Restart services to apply new settings")
        logger.info("   Run: docker-compose restart backend worker_vatican beat redis\n")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Redis cleanup failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\n\n⚠️ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Fatal error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
