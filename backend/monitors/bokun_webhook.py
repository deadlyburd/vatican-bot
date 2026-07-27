"""
Bokun Webhook Handler

Receives booking notifications from Bokun and syncs to Google Sheets.
The bot then reads from Google Sheets to automatically complete Vatican bookings.

Webhook URL: http://YOUR_SERVER_IP:8000/api/v1/bokun/webhook/
"""

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
import logging
from datetime import datetime
from backend.services.bokun_sheets_sync import get_bokun_sync
from .models import MonitorTask, Agency

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def bokun_webhook(request):
    """
    Receive booking notifications from Bokun
    
    Expected payload from Bokun:
    {
        "event": "booking.created",
        "booking": {
            "id": "BK12345",
            "product": {
                "title": "Vatican Museums Tickets",
                "date": "2026-06-15",
                "time": "10:00"
            },
            "participants": 2,
            "customer": {
                "firstName": "John",
                "lastName": "Doe",
                "email": "john@example.com",
                "phone": "+393331234567"
            },
            "guests": [
                {
                    "firstName": "John",
                    "lastName": "Doe",
                    "dateOfBirth": "1990-01-01",
                    "gender": "MALE"
                },
                {
                    "firstName": "Jane",
                    "lastName": "Doe",
                    "dateOfBirth": "1992-05-15",
                    "gender": "FEMALE"
                }
            ],
            "status": "CONFIRMED",
            "createdAt": "2026-05-26T10:30:00Z"
        }
    }
    """
    try:
        # Parse request body
        data = json.loads(request.body)
        logger.info(f"📥 Received Bokun webhook: {data.get('event')}")
        
        event = data.get('event')
        booking = data.get('booking', {})
        
        # Only process booking.created events
        if event != 'booking.created':
            logger.info(f"⏭️ Ignoring event: {event}")
            return JsonResponse({
                'status': 'ignored',
                'message': f'Event {event} not processed'
            })
        
        # Extract booking data
        booking_id = booking.get('id', f"BK{datetime.now().strftime('%Y%m%d%H%M%S')}")
        product = booking.get('product', {})
        customer = booking.get('customer', {})
        guests = booking.get('guests', [])
        
        # Convert date format: 2026-06-15 → 15/06/2026
        date_str = product.get('date', '')
        if date_str:
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                date_formatted = date_obj.strftime('%d/%m/%Y')
            except:
                date_formatted = date_str
        else:
            date_formatted = ''
        
        # Prepare data for Google Sheets
        sheets_data = {
            'booking_id': booking_id,
            'date': date_formatted,
            'time': product.get('time', '10:00'),
            'visitors': booking.get('participants', len(guests)),
            'ticket_type': product.get('title', 'Vatican Museums - Standard Entry'),
            'customer': {
                'first_name': customer.get('firstName', ''),
                'last_name': customer.get('lastName', ''),
                'email': customer.get('email', ''),
                'phone': customer.get('phone', '')
            },
            'participants': [
                {
                    'first_name': guest.get('firstName', ''),
                    'last_name': guest.get('lastName', ''),
                    'birth_date': guest.get('dateOfBirth', ''),
                    'gender': 'M' if guest.get('gender') == 'MALE' else 'F'
                }
                for guest in guests
            ],
            'status': 'Pending',
            'created_at': booking.get('createdAt', datetime.now().isoformat())
        }
        
        # Sync to Google Sheets
        sync = get_bokun_sync()
        success = sync.add_booking_from_bokun(sheets_data)
        
        if success:
            logger.info(f"✅ Booking {booking_id} synced to Google Sheets")
            
            # Optionally: Create monitoring task automatically
            # (Uncomment if you want automatic task creation)
            # create_monitoring_task_from_booking(sheets_data)
            
            return JsonResponse({
                'status': 'success',
                'message': f'Booking {booking_id} synced to Google Sheets',
                'booking_id': booking_id
            })
        else:
            logger.error(f"❌ Failed to sync booking {booking_id}")
            return JsonResponse({
                'status': 'error',
                'message': 'Failed to sync to Google Sheets'
            }, status=500)
        
    except Exception as e:
        logger.error(f"❌ Bokun webhook error: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


def create_monitoring_task_from_booking(booking_data: dict):
    """
    Automatically create a monitoring task from a booking
    
    This is optional - you can also manually create tasks or
    have the bot read from Google Sheets periodically.
    """
    try:
        # Get default agency (or determine from booking data)
        agency = Agency.objects.filter(is_active=True).first()
        
        if not agency:
            logger.warning("⚠️ No active agency found")
            return
        
        # Create monitoring task
        task = MonitorTask.objects.create(
            agency=agency,
            site='vatican',
            area_name='Vatican Museums',
            dates=[booking_data['date']],  # Single date from booking
            preferred_times=[booking_data['time']],
            visitors=booking_data['visitors'],
            adult_count=booking_data['visitors'],
            child_count=0,
            ticket_type=0,  # Standard ticket
            ticket_name='Vatican Museums - Standard Entry',
            check_interval=300,  # Check every 5 minutes
            tier='snipe',
            is_active=True,
            notification_mode='available_only'
        )
        
        logger.info(f"✅ Created monitoring task {task.id} for booking {booking_data['booking_id']}")
        
        # Update Google Sheets status
        sync = get_bokun_sync()
        sync.update_booking_status(
            booking_data['booking_id'],
            'Monitoring',
            notes=f'Bot monitoring task created (ID: {task.id})'
        )
        
    except Exception as e:
        logger.error(f"Failed to create monitoring task: {e}")


@csrf_exempt
@require_http_methods(["GET"])
def bokun_webhook_test(request):
    """
    Test endpoint to verify webhook is working
    """
    return JsonResponse({
        'status': 'ok',
        'message': 'Bokun webhook endpoint is active',
        'timestamp': datetime.now().isoformat()
    })
