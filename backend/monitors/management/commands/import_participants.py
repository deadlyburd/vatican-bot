"""
Import participants from Google Sheets
Usage: python manage.py import_participants --agency=WOR
"""
from django.core.management.base import BaseCommand
from monitors.models import Agency, BuyerProfile
from services.google_sheets_service import get_sheets_service
import json


class Command(BaseCommand):
    help = 'Import participants from Google Sheets'
    
    def add_arguments(self, parser):
        parser.add_argument('--agency', type=str, help='Agency name')
        parser.add_argument('--sheet-url', type=str, help='Google Sheet URL (optional)')
        parser.add_argument('--dry-run', action='store_true', help='Preview without saving')
    
    def handle(self, *args, **options):
        agency_name = options.get('agency')
        sheet_url = options.get('sheet_url')
        dry_run = options.get('dry_run', False)
        
        if not agency_name:
            self.stdout.write(self.style.ERROR('❌ --agency is required'))
            return
        
        # Get agency
        try:
            agency = Agency.objects.get(name__iexact=agency_name)
        except Agency.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ Agency "{agency_name}" not found'))
            return
        
        # Get Google Sheets service
        sheets_service = get_sheets_service()
        
        # Get sheet URL
        if not sheet_url:
            sheet_url = agency.google_sheet_url
        
        if not sheet_url:
            self.stdout.write(self.style.ERROR('❌ No Google Sheet URL provided'))
            self.stdout.write('Use: --sheet-url=<URL> or set agency.google_sheet_url')
            return
        
        # Import participants
        self.stdout.write(f'📊 Importing participants from Google Sheet...')
        participants = sheets_service.get_participants_from_sheet(sheet_url)
        
        if not participants:
            self.stdout.write(self.style.WARNING('⚠️ No participants found in sheet'))
            return
        
        self.stdout.write(f'✅ Found {len(participants)} participants:')
        
        for i, p in enumerate(participants, 1):
            self.stdout.write(f"  {i}. {p['first_name']} {p['last_name']} ({p.get('notes', 'N/A')})")
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN - No changes made'))
            return
        
        # Update agency's Google Sheet URL if provided
        if sheet_url and sheet_url != agency.google_sheet_url:
            agency.google_sheet_url = sheet_url
            agency.save(update_fields=['google_sheet_url'])
            self.stdout.write(f'✅ Updated agency Google Sheet URL')
        
        # Store participants in agency's buyer profile
        try:
            profile = BuyerProfile.objects.get(agency=agency)
            profile.participants_json = json.dumps(participants)
            profile.save(update_fields=['participants_json'])
            self.stdout.write(self.style.SUCCESS(f'✅ Saved {len(participants)} participants to BuyerProfile'))
        except BuyerProfile.DoesNotExist:
            self.stdout.write(self.style.WARNING('⚠️ No BuyerProfile found for agency'))
            self.stdout.write('Create one via Telegram bot first')
