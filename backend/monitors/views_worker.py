from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.utils import timezone
from .models import MonitorTask, HeldSlot, Agency, BuyerProfile
import json

@api_view(['GET'])
@permission_classes([AllowAny]) # In production, use API Key authentication
def get_pending_snipes(request):
    """Worker polls this to find a snipe task to execute."""
    tasks = MonitorTask.objects.filter(
        remote_worker_needed=True,
        is_active=True,
        tier='snipe'
    ).exclude(last_status='available') # Only check tasks that haven't hit yet or are actively scanning
    
    # Actually, the internal scanner usually finds the slot and then we need a worker to HOLD it.
    # OR, the worker scans directly. Let's assume the Worker is the one doing the heavy lifting 
    # for specific high-value dates.
    
    pending = []
    for t in tasks:
        # Check if claimed recently (last 5 mins) to avoid double-claiming
        if t.remote_worker_claimed and (timezone.now() - t.remote_worker_claimed).total_seconds() < 300:
            continue
            
        # Get profile data
        profile = BuyerProfile.objects.filter(agency=t.agency).first()
        profile_data = {}
        if profile:
            profile_data = {
                'first_name': profile.first_name,
                'last_name': profile.last_name,
                'email': profile.email,
                'phone': profile.phone,
                'city': profile.city,
            }
            
        pending.append({
            'id': t.id,
            'date': t.dates[0] if t.dates else None,
            'visitors': t.visitors,
            'adults': t.adult_count,
            'children': t.child_count,
            'preferred_times': t.preferred_times,
            'profile': profile_data
        })
        
    return Response({'tasks': pending})

@api_view(['POST'])
@permission_classes([AllowAny])
def claim_snipe(request, task_id):
    """Mark a task as being handled by a worker."""
    try:
        task = MonitorTask.objects.get(id=task_id)
        task.remote_worker_claimed = timezone.now()
        task.save()
        return Response({'status': 'ok'})
    except MonitorTask.DoesNotExist:
        return Response({'status': 'error', 'message': 'Task not found'}, status=404)

@api_view(['POST'])
@permission_classes([AllowAny])
def record_remote_hold(request):
    """Worker calls this once it successfully holds a slot in nodriver."""
    data = request.data
    task_id = data.get('task_id')
    try:
        task = MonitorTask.objects.get(id=task_id)
        hold = HeldSlot.objects.create(
            task=task,
            date=data.get('date'),
            slot_id=data.get('slot_id'),
            slot_time=data.get('slot_time'),
            ticket_id=data.get('ticket_id'),
            ticket_name=data.get('ticket_name', 'Vatican Ticket'),
            visitors=data.get('visitors', 1),
            jsessionid='REMOTE_SESSION',
            status='held',
            notes=json.dumps({'worker_node': data.get('worker_name', 'unknown')})
        )
        return Response({'status': 'ok', 'hold_id': hold.id})
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=400)

@api_view(['GET'])
@permission_classes([AllowAny])
def check_payment_signal(request, hold_id):
    """Worker polls this while holding to see if it should break and show payment page."""
    try:
        hold = HeldSlot.objects.get(id=hold_id)
        return Response({
            'payment_ready': hold.payment_ready,
            'status': hold.status
        })
    except HeldSlot.DoesNotExist:
        return Response({'status': 'error', 'message': 'Hold not found'}, status=404)
