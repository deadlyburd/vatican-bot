"""
Setup Bokun Integration

This command:
1. Tests Bokun API connection
2. Tests Google Sheets connection
3. Fetches sample bookings
4. Creates periodic sync tasks
5. Verifies complete integration
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_celery_beat.models import PeriodicTask, IntervalSchedule
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Setup and test Bokun → Google Sheets → Bot integration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test-only',
            action='store_true',
            help='Only test connections, do not create periodic tasks'
        )
        parser.add_argument(
            '--sync-now',
            action='store_true',
            help='Sync bookings immediately'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🚀 Setting up Bokun Integration...\n'))
        
        # Step 1: Test Bokun API
        self.stdout.write('📡 Step 1: Testing Bokun API connection...')
        if not self.test_bokun_api():
            self.stdout.write(self.style.ERROR('❌ Bokun API test failed!'))
            return
        self.stdout.write(self.style.SUCCESS('✅ Bokun API connected\n'))
        
        # Step 2: Test Google Sheets
        self.stdout.write('📊 Step 2: Testing Google Sheets connection...')
        if not self.test_google_sheets():
            self.stdout.write(self.style.ERROR('❌ Google Sheets test failed!'))
            return
        self.stdout.write(self.style.SUCCESS('✅ Google Sheets connected\n'))
        
        # Step 3: Fetch sample bookings
        self.stdout.write('📥 Step 3: Fetching sample bookings from Bokun...')
        bookings = self.fetch_sample_bookings()
        self.stdout.write(self.style.SUCCESS(f'✅ Found {len(bookings)} bookings\n'))
        
        if bookings:
            self.stdout.write('Sample booking:')
            booking = bookings[0]
            self.stdout.write(f"  ID: {booking.get('confirmationCode', 'N/A')}")
            self.stdout.write(f"  Product: {booking.get('product', {}).get('title', 'N/A')}")
            self.stdout.write(f"  Date: {booking.get('startTime', 'N/A')}")
            self.stdout.write('')
        
        # Step 4: Sync to Sheets (if requested)
        if options['sync_now']:
            self.stdout.write('🔄 Step 4: Syncing bookings to Google Sheets...')
            synced = self.sync_bookings()
            self.stdout.write(self.style.SUCCESS(f'✅ Synced {synced} bookings\n'))
        
        # Step 5: Create periodic tasks (if not test-only)
        if not options['test_only']:
            self.stdout.write('⏰ Step 5: Creating periodic sync tasks...')
            self.create_periodic_tasks()
            self.stdout.write(self.style.SUCCESS('✅ Periodic tasks created\n'))
        
        # Summary
        self.stdout.write(self.style.SUCCESS('\n🎉 Bokun Integration Setup Complete!\n'))
        self.stdout.write('Next steps:')
        self.stdout.write('1. Bokun will sync bookings every 5 minutes')
        self.stdout.write('2. Bot will create monitoring tasks automatically')
        self.stdout.write('3. Check logs: docker-compose logs -f worker_vatican | grep "Bokun"')
        self.stdout.write('')
    
    def test_bokun_api(self):
        """Test Bokun API connection"""
        try:
            from backend.services.bokun_api import get_bokun_api
            
            api = get_bokun_api()
            return api.test_connection()
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))
            return False
    
    def test_google_sheets(self):
        """Test Google Sheets connection"""
        try:
            from backend.services.bokun_sheets_sync import get_bokun_sync
            
            sync = get_bokun_sync()
            
            # Try to get pending bookings (will fail if not connected)
            sync.get_pending_bookings()
            
            return True
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))
            return False
    
    def fetch_sample_bookings(self):
        """Fetch sample bookings from Bokun"""
        try:
            from backend.services.bokun_api import get_bokun_api
            from datetime import datetime, timedelta
            
            api = get_bokun_api()
            
            # Fetch bookings for next 7 days
            bookings = api.get_confirmed_bookings(
                from_date=datetime.now(),
                to_date=datetime.now() + timedelta(days=7)
            )
            
            return bookings
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))
            return []
    
    def sync_bookings(self):
        """Sync bookings to Google Sheets"""
        try:
            from backend.services.bokun_api import get_bokun_api
            from datetime import datetime, timedelta
            
            api = get_bokun_api()
            
            # Sync bookings for next 90 days
            synced = api.sync_bookings_to_sheets(
                from_date=datetime.now(),
                to_date=datetime.now() + timedelta(days=90)
            )
            
            return synced
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))
            return 0
    
    def create_periodic_tasks(self):
        """Create periodic tasks for Bokun sync"""
        try:
            # Create 5-minute interval
            schedule, created = IntervalSchedule.objects.get_or_create(
                every=5,
                period=IntervalSchedule.MINUTES
            )
            
            # Task 1: Bokun → Sheets sync
            task1, created1 = PeriodicTask.objects.get_or_create(
                name='Sync Bokun to Google Sheets',
                defaults={
                    'task': 'sync_bokun_to_sheets',
                    'interval': schedule,
                    'enabled': True
                }
            )
            
            if created1:
                self.stdout.write('  ✅ Created: Sync Bokun to Google Sheets (every 5 min)')
            else:
                self.stdout.write('  ℹ️ Already exists: Sync Bokun to Google Sheets')
            
            # Task 2: Sheets → Monitoring sync
            task2, created2 = PeriodicTask.objects.get_or_create(
                name='Sync Sheets to Monitoring Tasks',
                defaults={
                    'task': 'sync_sheets_to_monitoring',
                    'interval': schedule,
                    'enabled': True
                }
            )
            
            if created2:
                self.stdout.write('  ✅ Created: Sync Sheets to Monitoring Tasks (every 5 min)')
            else:
                self.stdout.write('  ℹ️ Already exists: Sync Sheets to Monitoring Tasks')
            
            return True
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))
            return False
