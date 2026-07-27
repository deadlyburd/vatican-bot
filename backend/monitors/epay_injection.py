"""
Browser-Compatible Epay Link Injection with Participant Data
===============================================================
Generates epay links that work in any browser with embedded participant information.
Uses URL parameters, localStorage, or sessionStorage for data injection.
"""

import json
import base64
import urllib.parse
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(['POST'])
def generate_browser_epay_link(request):
    """
    Generate browser-compatible epay link with embedded participant data.
    
    Payload:
    {
      "hold_id": 123,
      "participants": [
        {"first_name": "Mario", "last_name": "Rossi", "email": "mario@example.com", ...},
        ...
      ],
      "buyer": {
        "first_name": "Luigi", "last_name": "Verdi", "email": "luigi@example.com", ...
      },
      "injection_method": "url" | "localstorage" | "sessionstorage"  # default: url
    }
    """
    from .models import HeldSlot
    
    try:
        hold_id = request.data.get('hold_id')
        participants = request.data.get('participants', [])
        buyer_data = request.data.get('buyer', {})
        injection_method = request.data.get('injection_method', 'url')
        
        if not hold_id:
            return Response({'error': 'hold_id is required'}, status=400)
        
        # Get the held slot
        held_slot = HeldSlot.objects.select_related('task__agency').get(id=hold_id, status='held')
        
        # Get the base epay URL from the held slot
        base_epay_url = held_slot.payment_url
        if not base_epay_url:
            return Response({'error': 'No payment URL available for this hold'}, status=400)
        
        # Prepare injection data
        injection_data = {
            'hold_id': hold_id,
            'slot_date': str(held_slot.date),
            'slot_time': held_slot.slot_time,
            'visitors': held_slot.visitors,
            'participants': participants,
            'buyer': buyer_data,
            'agency': held_slot.task.agency.name,
            'generated_at': str(held_slot.last_keepalive_at)
        }
        
        # Generate the browser-compatible URL based on injection method
        final_url = _generate_browser_url(base_epay_url, injection_data, injection_method)
        
        return Response({
            'status': 'success',
            'epay_url': final_url,
            'injection_method': injection_method,
            'hold_id': hold_id,
            'participant_count': len(participants),
            'expires_at': str(held_slot.hold_expires_at) if held_slot.hold_expires_at else None,
            'instructions': _get_injection_instructions(injection_method)
        })
        
    except HeldSlot.DoesNotExist:
        return Response({'error': 'Hold not found or expired'}, status=404)
    except Exception as e:
        return Response({'error': f'Failed to generate browser epay link: {str(e)}'}, status=500)

def _generate_browser_url(base_url, injection_data, method):
    """Generate browser-compatible URL with participant data injection"""
    
    if method == 'url':
        # URL parameter injection (simplest for browsers)
        encoded_data = base64.urlsafe_b64encode(
            json.dumps(injection_data).encode('utf-8')
        ).decode('utf-8')
        
        # Add as query parameter
        parsed_url = urllib.parse.urlparse(base_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        query_params['injection_data'] = [encoded_data]
        
        new_query = urllib.parse.urlencode(query_params, doseq=True)
        return urllib.parse.urlunparse(parsed_url._replace(query=new_query))
    
    elif method == 'localstorage':
        # localStorage injection (requires JavaScript)
        encoded_data = base64.urlsafe_b64encode(
            json.dumps(injection_data).encode('utf-8')
        ).decode('utf-8')
        
        # Create URL with hash fragment for JavaScript injection
        return f"{base_url}#injection=localstorage&data={encoded_data}"
    
    elif method == 'sessionstorage':
        # sessionStorage injection (requires JavaScript)
        encoded_data = base64.urlsafe_b64encode(
            json.dumps(injection_data).encode('utf-8')
        ).decode('utf-8')
        
        return f"{base_url}#injection=sessionstorage&data={encoded_data}"
    
    else:
        # Default to URL parameters
        return _generate_browser_url(base_url, injection_data, 'url')

def _get_injection_instructions(method):
    """Get instructions for the chosen injection method"""
    
    instructions = {
        'url': 'Data embedded in URL parameters. Open directly in browser.',
        'localstorage': 'Data stored in localStorage. Requires JavaScript execution.',
        'sessionstorage': 'Data stored in sessionStorage. Requires JavaScript execution.'
    }
    
    return instructions.get(method, instructions['url'])

@api_view(['GET'])
def decode_injection_data(request):
    """
    Decode injection data from URL parameters.
    Useful for testing and debugging injection payloads.
    """
    encoded_data = request.GET.get('injection_data')
    
    if not encoded_data:
        return Response({'error': 'No injection_data parameter found'}, status=400)
    
    try:
        # Decode the base64 data
        decoded_bytes = base64.urlsafe_b64decode(encoded_data)
        injection_data = json.loads(decoded_bytes.decode('utf-8'))
        
        return Response({
            'status': 'success',
            'injection_data': injection_data,
            'raw_encoded': encoded_data
        })
        
    except Exception as e:
        return Response({'error': f'Failed to decode injection data: {str(e)}'}, status=400)

# JavaScript injection template for browser execution
BROWSER_INJECTION_SCRIPT = """
// Vatican Epay Participant Data Injection
// Auto-executes when page loads to populate form fields

(function() {
    try {
        // Get injection data from URL hash
        const hashParams = new URLSearchParams(window.location.hash.substring(1));
        const injectionType = hashParams.get('injection');
        const encodedData = hashParams.get('data');
        
        if (!encodedData) return;
        
        // Decode base64 data
        const jsonData = atob(encodedData);
        const injectionData = JSON.parse(jsonData);
        
        // Store in appropriate storage
        if (injectionType === 'localstorage') {
            localStorage.setItem('vatican_injection_data', jsonData);
        } else if (injectionType === 'sessionstorage') {
            sessionStorage.setItem('vatican_injection_data', jsonData);
        }
        
        // Auto-fill form fields if on payment page
        setTimeout(() => {
            _autoFillParticipantData(injectionData);
        }, 1000);
        
    } catch (error) {
        console.error('Vatican injection error:', error);
    }
})();

function _autoFillParticipantData(data) {
    // Implementation for auto-filling Vatican payment forms
    // This would be customized based on the actual Vatican form structure
    console.log('Auto-filling participant data:', data);
}
"""

def generate_injection_script(request):
    """
    Return the JavaScript injection script as a downloadable file.
    """
    from django.http import HttpResponse
    
    response = HttpResponse(BROWSER_INJECTION_SCRIPT, content_type='application/javascript')
    response['Content-Disposition'] = 'attachment; filename="vatican_injection.js"'
    return response