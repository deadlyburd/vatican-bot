"""
Epay Payment Proxy View
========================
Flow:
1. Snipe/book generates a proxy URL: /pay/{hold_id}/{token}/
2. User opens URL in any browser
3. Server runs FRESH session chain: search → recap → turnstile → reservation
4. Server redirects browser to epay.catholica.va
5. User fills card and pays

Key: ALWAYS use a fresh session (never reuse stale DB cookies).
     This is what eliminates the 500 error.
"""
import json
import logging
import os
import secrets
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.cache import cache

logger = logging.getLogger(__name__)

BASE = 'https://tickets.museivaticani.va'
H_XHR = {
    'Accept': 'application/json, text/plain, */*',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': f'{BASE}/',
    'Origin': BASE,
    'Content-Type': 'application/json',
}
HC = {**H_XHR, 'Referer': f'{BASE}/home/checkout'}
del HC['X-Requested-With']


def _do_fresh_reservation(held, participants=None, representative=None, profile=None):
    """
    Run the full fresh chain: search → timeavail → recap → turnstile → reservation.
    Returns (epay_url, reference) or raises RuntimeError.
    """
    from monitors.epay_ssl import make_vatican_session
    from monitors.turnstile_pool import get_token_sync

    s = make_vatican_session()

    # Step 1: Search → fresh ticket_id + JSESSIONID
    r = s.get(f'{BASE}/api/search/resultPerTag', params={
        'lang': 'it', 'visitorNum': str(held.visitors),
        'visitDate': held.date, 'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
    }, headers=H_XHR, timeout=12)
    if r.status_code != 200:
        raise RuntimeError(f"Search API {r.status_code}")

    fresh_ticket = next(
        (v for v in r.json().get('visits', [])
         if 'musei vaticani' in v.get('name', '').lower()
         and 'ingresso' in v.get('name', '').lower()),
        None
    )
    ticket_id = int(fresh_ticket['id']) if fresh_ticket else int(held.ticket_id)
    logger.info(f"  Fresh ticket_id={ticket_id}")

    # Step 2: Timeavail → find the slot_id for our time
    r2 = s.get(f'{BASE}/api/visit/timeavail', params={
        'lang': 'it', 'visitLang': '', 'visitTypeId': str(ticket_id),
        'visitorNum': str(held.visitors), 'visitDate': held.date,
    }, headers=H_XHR, timeout=10)

    slot_id = held.slot_id  # fallback
    if r2.status_code == 200:
        timetable = r2.json().get('timetable', [])
        # Try to find matching time slot
        match = next(
            (sl for sl in timetable
             if sl.get('time') == held.slot_time
             and sl.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')),
            None
        )
        if match:
            slot_id = str(match['id'])
            logger.info(f"  Fresh slot_id={slot_id} for {held.slot_time}")
        else:
            logger.warning(f"  Slot {held.slot_time} not found in fresh timeavail — using stored slot_id")

    # Step 3: Recap
    recap_body = {
        "visitId": str(slot_id),
        "visitTypeId": int(ticket_id),
        "visitorNum": int(held.visitors),
        "lang": "it",
        "tickets": [
            {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(held.visitors)},
            {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": 0},
        ],
        "additionalCosts": {
            "service-0": {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(held.visitors)}
        },
        "services": [
            {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(held.visitors)}
        ]
    }
    rr = s.post(f'{BASE}/api/visit/recap', json=recap_body, headers=HC, timeout=12)
    if rr.status_code != 200:
        raise RuntimeError(f"Recap {rr.status_code}: {rr.text[:200]}")

    rd = rr.json()
    recap_id = rd.get('recapId') or rd.get('id') or ''
    total = rd.get('total', 0)
    logger.info(f"  Recap OK: {recap_id} €{total}")

    # Update DB with fresh IDs
    held.recap_id = recap_id
    held.ticket_id = str(ticket_id)
    held.slot_id = str(slot_id)
    new_jsid = s.cookies.get('JSESSIONID', '')
    if new_jsid:
        held.jsessionid = new_jsid
        held.ticketmv = s.cookies.get('ticketmv', '') or held.ticketmv
    held.save(update_fields=['recap_id', 'ticket_id', 'slot_id', 'jsessionid', 'ticketmv'])

    # Step 4: Turnstile token
    token = get_token_sync()
    if not token:
        raise RuntimeError("Turnstile solve failed — no token available")
    logger.info(f"  Token ready ({len(token)} chars, prefix={token[:2]})")

    # Step 5: Build participant list
    service_ids = [58]
    if participants:
        participant_list = []
        for p in participants[:held.visitors]:
            first = (p.get('first_name') or '').strip() or (profile.first_name if profile else 'Visitor')
            last = (p.get('last_name') or '').strip() or (profile.last_name if profile else 'Vatican')
            participant_list.append({'name': first, 'surname': last, 'id': 60, 'ticketType': 'intero', 'services': service_ids})
        while len(participant_list) < held.visitors:
            participant_list.append({
                'name': profile.first_name if profile else 'Visitor',
                'surname': profile.last_name if profile else 'Vatican',
                'id': 60, 'ticketType': 'intero', 'services': service_ids,
            })
    elif profile:
        participant_list = profile.to_participant_list(held.visitors, ticket_id=60, service_ids=service_ids)
    else:
        participant_list = [
            {'name': ' ', 'surname': ' ', 'id': 60, 'ticketType': 'intero', 'services': service_ids}
            for _ in range(held.visitors)
        ]

    # Build representative
    if representative and profile:
        rep = {
            'name': representative.get('first_name') or profile.first_name,
            'surname': representative.get('last_name') or profile.last_name,
            'gender': representative.get('gender') or profile.gender,
            'country': representative.get('country') or profile.country,
            'city': representative.get('city') or profile.city,
            'birthDate': representative.get('birth_date') or (
                profile.birth_date.strftime('%Y-%m-%dT%H:%M:%S.000Z') if profile.birth_date else None
            ),
            'email': representative.get('email') or profile.email,
            'confirmEmail': representative.get('email') or profile.email,
            'telephoneNumber': representative.get('phone') or profile.phone,
            'language': representative.get('language') or profile.language or 'it',
        }
    elif profile:
        rep = profile.to_representative_user()
    else:
        rep = {}

    # Step 6: Reservation
    res_body = {
        "recaptcha": token,
        "lang": "it",
        "recapId": recap_id,
        "visitorNum": int(held.visitors),
        "visitId": str(slot_id),
        "visitTypeId": int(ticket_id),
        "tickets": [
            {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(held.visitors)},
            {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": 0},
        ],
        "services": [
            {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(held.visitors)}
        ],
        "representativeUser": rep,
        "participantUser": participant_list,
        "gdpr": [{"id": 1, "check": True}, {"id": 3, "check": False}],
    }

    res_r = s.post(f'{BASE}/api/visit/reservation', json=res_body, headers=HC, timeout=20)
    logger.info(f"  Reservation HTTP {res_r.status_code}")

    if res_r.status_code != 200:
        raise RuntimeError(f"Reservation {res_r.status_code}: {res_r.text[:300]}")

    res_data = res_r.json()
    epay = res_data.get('epay', {})
    # epay.url = https://epay.catholica.va/pay/SIV001/upp/auth/start.page
    # epay.urlMs = https://tickets.museivaticani.va/epay/process/{referenceOrder}
    # epay.mac_avvio = MAC for the POST to start.page
    epay_url = epay.get('url') or res_data.get('paymentUrl') or ''
    reference = res_data.get('referenceOrder', '')
    mac_avvio = epay.get('mac_avvio', '')
    id_negozio = epay.get('idnegozio', 'SIV001')
    valuta = epay.get('valuta', '978')
    tcontab = epay.get('tcontab', 'D')
    tautor = epay.get('tautor', 'I')
    url_ms = epay.get('urlMs', '')
    url_done = epay.get('urldone', '')
    url_back = epay.get('urlback', '')

    if not epay_url:
        raise RuntimeError(f"No epay URL in response: {json.dumps(res_data)[:300]}")

    return epay_url, reference, total, {
        'mac_avvio': mac_avvio,
        'idnegozio': id_negozio,
        'valuta': valuta,
        'tcontab': tcontab,
        'tautor': tautor,
        'urlMs': url_ms,
        'urldone': url_done,
        'urlback': url_back,
        'referenceOrder': reference,
    }


@csrf_exempt
@require_http_methods(["GET"])
def epay_direct(request, hold_id, token):
    """
    GET /pay/direct/<hold_id>/<token>/
    Serves the epay POST form directly from cached reservation params.
    NO second reservation needed — uses the epay params from the snipe.
    Single-use, expires in 1 hour.
    """
    cache_key = f"epay_direct:{hold_id}:{token}"
    data = cache.get(cache_key)
    if not data:
        return HttpResponse(_error_page("Link expired or invalid.",
            "Payment links expire after 1 hour. Ask admin for a new link."), status=410)

    epay_url = data.get('epay_url', '')
    epay_params = data.get('epay_params', {})
    reference = data.get('reference', '')

    if not epay_url or not epay_params.get('mac_avvio'):
        return HttpResponse(_error_page("Invalid payment data.", "Contact admin."), status=500)

    cache.delete(cache_key)  # single-use
    logger.info(f"✅ Epay direct Hold #{hold_id} ref={reference}")
    return HttpResponse(_epay_post_form(epay_url, reference, epay_params), content_type='text/html')


@csrf_exempt
@require_http_methods(["GET"])
def epay_redirect(request, hold_id, token):
    """
    GET /pay/<hold_id>/<token>/
    Opens in any browser. Runs fresh session chain, redirects to epay.
    """
    from monitors.models import HeldSlot, BuyerProfile

    cache_key = f"epay_token:{hold_id}:{token}"
    token_data = cache.get(cache_key)
    if not token_data:
        return HttpResponse(_error_page("Link expired or invalid.",
            "Payment links expire after 1 hour. Ask admin for a new link."), status=410)

    try:
        held = HeldSlot.objects.select_related('task__agency').get(id=hold_id)
    except HeldSlot.DoesNotExist:
        return HttpResponse(_error_page("Hold not found.", ""), status=404)

    if held.status not in ('held', 'paying'):
        return HttpResponse(_error_page(
            f"Hold #{hold_id} is {held.status}.",
            "This slot is no longer available."), status=410)

    # Show loading page on first hit, process on second
    if request.GET.get('processing') != '1':
        return HttpResponse(_loading_page(hold_id, token), content_type='text/html')

    participants = token_data.get('participants', [])
    representative = token_data.get('representative', {})

    try:
        profile = BuyerProfile.objects.get(agency=held.task.agency)
    except BuyerProfile.DoesNotExist:
        profile = None

    try:
        epay_url, reference, total, epay_params = _do_fresh_reservation(
            held, participants=participants, representative=representative, profile=profile
        )
    except RuntimeError as e:
        logger.error(f"Reservation failed for Hold #{hold_id}: {e}")
        return HttpResponse(_error_page("Reservation failed.", str(e)), status=500)

    held.status = 'paying'
    held.payment_url = epay_url
    held.save(update_fields=['status', 'payment_url'])
    cache.delete(cache_key)  # single-use

    logger.info(f"✅ Epay redirect Hold #{hold_id} ref={reference} → {epay_url[:60]}")

    # Vatican epay requires a POST form to start.page with MAC params
    mac = epay_params.get('mac_avvio', '')
    if mac:
        return HttpResponse(_epay_post_form(epay_url, reference, epay_params), content_type='text/html')
    return HttpResponseRedirect(epay_url)


@csrf_exempt
@require_http_methods(["POST"])
def generate_payment_link(request):
    """
    POST /api/v1/generate-payment-link/
    Body: { "hold_id": 123, "participants": [...], "representative": {...}, "expires_in": 3600 }
    Returns: { "payment_url": "https://hydrabot.it/pay/123/token/" }
    """
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    hold_id = data.get('hold_id')
    if not hold_id:
        return JsonResponse({'error': 'hold_id required'}, status=400)

    try:
        from monitors.models import HeldSlot
        held = HeldSlot.objects.get(id=hold_id)
    except HeldSlot.DoesNotExist:
        return JsonResponse({'error': f'Hold #{hold_id} not found'}, status=404)

    if held.status not in ('held', 'paying'):
        return JsonResponse({'error': f'Hold is {held.status}'}, status=410)

    token = secrets.token_urlsafe(32)
    expires_in = int(data.get('expires_in', 3600))

    cache.set(f"epay_token:{hold_id}:{token}", {
        'hold_id': hold_id,
        'participants': data.get('participants', []),
        'representative': data.get('representative', {}),
    }, timeout=expires_in)

    base_url = os.getenv('SERVER_BASE_URL', 'https://hydrabot.it')
    payment_url = f"{base_url}/pay/{hold_id}/{token}/"

    return JsonResponse({
        'payment_url': payment_url,
        'expires_in': expires_in,
        'hold_id': hold_id,
        'date': held.date,
        'time': held.slot_time,
        'visitors': held.visitors,
        'total': str(held.total_price or ''),
    })


def _epay_post_form(action, reference, epay_params):
    """
    Auto-submitting POST form to Vatican's epay start.page.
    Vatican requires a POST (not GET) with MAC params to initiate payment.
    Confirmed from epay.catholica.va.txt analysis.
    """
    mac = epay_params.get('mac_avvio', '')
    id_negozio = epay_params.get('idnegozio', 'SIV001')
    valuta = epay_params.get('valuta', '978')
    tcontab = epay_params.get('tcontab', 'D')
    tautor = epay_params.get('tautor', 'I')
    url_ms = epay_params.get('urlMs', '')
    url_done = epay_params.get('urldone', '')
    url_back = epay_params.get('urlback', '')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Vatican Museums — Redirecting to Payment</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{background:#0a0a0a;color:#fff;font-family:-apple-system,sans-serif;
    display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center}}
  .card{{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:16px;padding:48px 40px;max-width:420px;width:90%}}
  .spinner{{width:48px;height:48px;border:3px solid #2a2a2a;border-top-color:#22c55e;
    border-radius:50%;animation:spin .8s linear infinite;margin:0 auto 24px}}
  @keyframes spin{{to{{transform:rotate(360deg)}}}}
  p{{color:#888;font-size:14px;margin-top:16px}}
</style>
</head>
<body>
<div class="card">
  <div style="font-size:48px;margin-bottom:16px">🏛️</div>
  <h1 style="font-size:20px;font-weight:600">Redirecting to payment...</h1>
  <div class="spinner" style="margin-top:24px"></div>
  <p>Ref: {reference}</p>
</div>
<form id="f" method="POST" action="{action}">
  <input type="hidden" name="idnegozio" value="{id_negozio}">
  <input type="hidden" name="codTrans" value="{reference}">
  <input type="hidden" name="divisa" value="{valuta}">
  <input type="hidden" name="tcontab" value="{tcontab}">
  <input type="hidden" name="tautor" value="{tautor}">
  <input type="hidden" name="mac" value="{mac}">
  <input type="hidden" name="url" value="{url_ms}">
  <input type="hidden" name="url_back" value="{url_back}">
  <input type="hidden" name="urlpost" value="{url_done}">
</form>
<script>document.getElementById('f').submit();</script>
</body>
</html>"""


def _loading_page(hold_id, token):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Vatican Museums — Completing Payment</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{background:#0a0a0a;color:#fff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center}}
  .card{{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:16px;padding:48px 40px;max-width:420px;width:90%}}
  .logo{{font-size:48px;margin-bottom:16px}}
  h1{{font-size:22px;font-weight:600;margin-bottom:8px}}
  p{{color:#888;font-size:14px;margin-bottom:24px;line-height:1.6}}
  .spinner{{width:48px;height:48px;border:3px solid #2a2a2a;border-top-color:#22c55e;
    border-radius:50%;animation:spin .8s linear infinite;margin:0 auto 24px}}
  @keyframes spin{{to{{transform:rotate(360deg)}}}}
  .step{{color:#22c55e;font-size:13px;font-weight:500}}
  .info{{color:#555;font-size:12px;margin-top:12px}}
</style>
</head>
<body>
<div class="card">
  <div class="logo">🏛️</div>
  <h1>Vatican Museums</h1>
  <p>Preparing your secure payment page.<br>Please wait ~30 seconds.</p>
  <div class="spinner"></div>
  <div class="step" id="step">Verifying reservation...</div>
  <div class="info">Do not close this tab</div>
</div>
<script>
  const steps=['Verifying reservation...','Solving security challenge...','Generating payment link...','Redirecting to payment...'];
  let i=0;const el=document.getElementById('step');
  setInterval(()=>{{i=Math.min(i+1,steps.length-1);el.textContent=steps[i];}},8000);
  setTimeout(()=>{{window.location.href='/pay/{hold_id}/{token}/?processing=1';}},1500);
</script>
</body>
</html>"""


def _error_page(title, detail):
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Payment Error</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{background:#0a0a0a;color:#fff;font-family:-apple-system,sans-serif;
    display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center}}
  .card{{background:#1a1a1a;border:1px solid #3a1a1a;border-radius:16px;padding:48px 40px;max-width:420px;width:90%}}
  .icon{{font-size:48px;margin-bottom:16px}}
  h1{{font-size:20px;font-weight:600;margin-bottom:12px;color:#ef4444}}
  p{{color:#888;font-size:14px;line-height:1.6}}
</style>
</head>
<body>
<div class="card">
  <div class="icon">❌</div>
  <h1>{title}</h1>
  <p>{detail}</p>
  <p style="margin-top:20px;color:#555;font-size:12px">Contact admin for assistance.</p>
</div>
</body>
</html>"""
