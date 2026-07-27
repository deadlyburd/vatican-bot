"""
Google Sheets Auto-Sync Tasks
Automatically syncs participant names from Google Sheets
"""
from celery import shared_task
from monitors.models import Agency, BuyerProfile
from services.google_sheets_service import get_sheets_service
import json
import logging

logger = logging.getLogger(__name__)


@shared_task
def sync_participants_from_sheets():
    """
    Auto-sync participants from Google Sheets every hour.
    Runs for all agencies that have google_sheet_url configured.
    """
    sheets_service = get_sheets_service()
    
    # Get all agencies with Google Sheet URLs
    agencies = Agency.objects.filter(
        google_sheet_url__isnull=False,
        is_active=True
    ).exclude(google_sheet_url='')
    
    total_synced = 0
    total_agencies = agencies.count()
    
    logger.info(f"🔄 Starting auto-sync for {total_agencies} agencies with Google Sheets")
    
    for agency in agencies:
        try:
            # Get participants from Google Sheet
            participants = sheets_service.get_participants_from_sheet(agency.google_sheet_url)
            
            if not participants:
                logger.warning(f"⚠️ No participants found for {agency.name}")
                continue
            
            # Get or create buyer profile
            try:
                profile = BuyerProfile.objects.get(agency=agency)
            except BuyerProfile.DoesNotExist:
                logger.warning(f"⚠️ No BuyerProfile found for {agency.name} - skipping")
                continue
            
            # Update participants
            profile.participants_json = json.dumps(participants)
            profile.save(update_fields=['participants_json'])
            
            total_synced += len(participants)
            logger.info(f"✅ Synced {len(participants)} participants for {agency.name}")
            
        except Exception as e:
            logger.error(f"❌ Failed to sync participants for {agency.name}: {e}")
    
    logger.info(f"🎉 Auto-sync complete: {total_synced} participants synced across {total_agencies} agencies")
    
    return {
        'success': True,
        'agencies_synced': total_agencies,
        'total_participants': total_synced
    }


@shared_task
def sync_participants_for_agency(agency_id):
    """
    Sync participants for a specific agency.
    Can be triggered manually or via webhook.
    
    Args:
        agency_id: ID of the agency to sync
    """
    sheets_service = get_sheets_service()
    
    try:
        agency = Agency.objects.get(id=agency_id, is_active=True)
        
        if not agency.google_sheet_url:
            logger.warning(f"⚠️ Agency {agency.name} has no Google Sheet URL")
            return {'success': False, 'error': 'No Google Sheet URL configured'}
        
        # Get participants from Google Sheet
        participants = sheets_service.get_participants_from_sheet(agency.google_sheet_url)
        
        if not participants:
            logger.warning(f"⚠️ No participants found for {agency.name}")
            return {'success': False, 'error': 'No participants found in sheet'}
        
        # Get buyer profile
        try:
            profile = BuyerProfile.objects.get(agency=agency)
        except BuyerProfile.DoesNotExist:
            logger.error(f"❌ No BuyerProfile found for {agency.name}")
            return {'success': False, 'error': 'No BuyerProfile found'}
        
        # Update participants
        profile.participants_json = json.dumps(participants)
        profile.save(update_fields=['participants_json'])
        
        logger.info(f"✅ Synced {len(participants)} participants for {agency.name}")
        
        return {
            'success': True,
            'agency': agency.name,
            'participants_count': len(participants),
            'participants': participants
        }
        
    except Agency.DoesNotExist:
        logger.error(f"❌ Agency {agency_id} not found")
        return {'success': False, 'error': 'Agency not found'}
    except Exception as e:
        logger.error(f"❌ Failed to sync participants for agency {agency_id}: {e}")
        return {'success': False, 'error': str(e)}
