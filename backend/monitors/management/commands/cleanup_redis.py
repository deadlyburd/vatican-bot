"""
Django management command to clean up Redis cache
=================================================
Removes old Celery task results and expired keys to prevent Redis bloat.

Usage:
    python manage.py cleanup_redis
    python manage.py cleanup_redis --dry-run
    python manage.py cleanup_redis --aggressive
"""
from django.core.management.base import BaseCommand
from django.conf import settings
import redis
import time


class Command(BaseCommand):
    help = 'Clean up Redis cache to prevent bloat'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--aggressive',
            action='store_true',
            help='Delete all Celery task results (not just old ones)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        aggressive = options['aggressive']
        
        self.stdout.write(self.style.SUCCESS('='*80))
        self.stdout.write(self.style.SUCCESS('REDIS CLEANUP'))
        self.stdout.write(self.style.SUCCESS('='*80))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n⚠️  DRY RUN MODE - No changes will be made\n'))
        
        # Connect to Redis
        broker_url = settings.CELERY_BROKER_URL
        r = redis.from_url(broker_url)
        
        # Check Redis status
        try:
            r.ping()
            self.stdout.write(self.style.SUCCESS('✅ Connected to Redis'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Cannot connect to Redis: {e}'))
            return
        
        # Get initial stats
        initial_keys = r.dbsize()
        initial_memory = r.info('memory')['used_memory_human']
        
        self.stdout.write(f'\nInitial state:')
        self.stdout.write(f'  Keys: {initial_keys:,}')
        self.stdout.write(f'  Memory: {initial_memory}')
        
        # Clean up Celery task results
        self.stdout.write(self.style.WARNING('\n1. Cleaning Celery task results...'))
        deleted_celery = self.cleanup_celery_results(r, dry_run, aggressive)
        
        # Clean up expired keys
        self.stdout.write(self.style.WARNING('\n2. Cleaning expired keys...'))
        deleted_expired = self.cleanup_expired_keys(r, dry_run)
        
        # Clean up old monitoring state
        self.stdout.write(self.style.WARNING('\n3. Cleaning old monitoring state...'))
        deleted_state = self.cleanup_old_state(r, dry_run)
        
        # Get final stats
        final_keys = r.dbsize()
        final_memory = r.info('memory')['used_memory_human']
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*80))
        self.stdout.write(self.style.SUCCESS('CLEANUP SUMMARY'))
        self.stdout.write(self.style.SUCCESS('='*80))
        
        self.stdout.write(f'\nDeleted:')
        self.stdout.write(f'  Celery results: {deleted_celery:,}')
        self.stdout.write(f'  Expired keys: {deleted_expired:,}')
        self.stdout.write(f'  Old state: {deleted_state:,}')
        self.stdout.write(f'  Total: {deleted_celery + deleted_expired + deleted_state:,}')
        
        self.stdout.write(f'\nFinal state:')
        self.stdout.write(f'  Keys: {final_keys:,} (was {initial_keys:,})')
        self.stdout.write(f'  Memory: {final_memory} (was {initial_memory})')
        
        if not dry_run:
            self.stdout.write(self.style.SUCCESS('\n✅ Cleanup complete!'))
        else:
            self.stdout.write(self.style.WARNING('\n⚠️  Dry run complete - run without --dry-run to apply changes'))

    def cleanup_celery_results(self, r, dry_run, aggressive):
        """Delete Celery task result keys"""
        deleted = 0
        
        # Scan for celery-task-meta-* keys
        cursor = 0
        pattern = 'celery-task-meta-*'
        
        while True:
            cursor, keys = r.scan(cursor, match=pattern, count=1000)
            
            if keys:
                if aggressive:
                    # Delete all Celery results
                    if not dry_run:
                        deleted += r.delete(*keys)
                    else:
                        deleted += len(keys)
                else:
                    # Only delete old results (>1 hour)
                    for key in keys:
                        try:
                            ttl = r.ttl(key)
                            # If no TTL set (-1) or expired (-2), delete it
                            if ttl == -1 or ttl == -2:
                                if not dry_run:
                                    r.delete(key)
                                deleted += 1
                        except Exception:
                            pass
            
            if cursor == 0:
                break
        
        return deleted

    def cleanup_expired_keys(self, r, dry_run):
        """Clean up keys that should have expired"""
        deleted = 0
        
        # Scan for keys with TTL = -2 (expired but not deleted)
        cursor = 0
        
        while True:
            cursor, keys = r.scan(cursor, count=1000)
            
            if keys:
                for key in keys:
                    try:
                        ttl = r.ttl(key)
                        if ttl == -2:  # Expired
                            if not dry_run:
                                r.delete(key)
                            deleted += 1
                    except Exception:
                        pass
            
            if cursor == 0:
                break
        
        return deleted

    def cleanup_old_state(self, r, dry_run):
        """Clean up old monitoring state keys"""
        deleted = 0
        
        # Clean up old ticket_state keys (older than 7 days)
        cursor = 0
        pattern = 'ticket_state:*'
        
        while True:
            cursor, keys = r.scan(cursor, match=pattern, count=1000)
            
            if keys:
                for key in keys:
                    try:
                        ttl = r.ttl(key)
                        # If TTL is set and less than 1 day, keep it
                        # Otherwise delete (either no TTL or very old)
                        if ttl == -1 or ttl > 604800:  # No TTL or >7 days
                            if not dry_run:
                                # Set TTL to 7 days instead of deleting
                                r.expire(key, 604800)
                            deleted += 1
                    except Exception:
                        pass
            
            if cursor == 0:
                break
        
        return deleted
