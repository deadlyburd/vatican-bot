
"""
Bulk Pre-Hold — May & June 2026
================================
Holds ALL available Vatican slots for May and June 2026 via /api/visit/recap.
Keeps them alive with keepalive pings every 4 minutes.
When you're ready to book, the recap is already done — just submit reservation.

Key facts:
- Vatican slot_id/ticket_id change daily → keepalive auto-refreshes them
- Each hold = 1 JSESSIONID session on Vatican's server
- Vatican allows ~24h holds before expiry
- Keepalive re-calls recap every 4 min to prevent expiry

Run:
    python bulk_prehold.py --scan          # scan and show available slots
    python bulk_prehold.py --hold          # hold all available slots
    python bulk_prehold.py --hold --visitors 2  # hold for 2 visitors
    python bulk_prehold.py --keepalive     # run keepalive loop (keep running)
    python bulk_prehold.py --status        # show all held slots
"""
import sys
import os
import time
import json
import requests
import argparse
import threading
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()

from monitors.models import HeldSlot, MonitorTask, Agency
from monitors.hold_manager import hold_slot, keepalive_slot
from django.utils import timezone

BASE = 'https://tickets.museivaticani.va'
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
H = {'Accept': 'application/json, text/plain, */*',
     'X-Requested-With': 'XMLHttpRequest',
     'Referer': f'{BASE}/', 'User-Agent': USER_AGENT}

# ── CONFIG ────────────────────────────────────────────────────────────────────
# Dates to pre-hold (all May + June 2026, skip Sundays)
START_DATE   = date(2026, 5, 1)
END_DATE     = date(2026, 6, 30)
VISITORS     = 2          # default visitors per hold
KEEPALIVE_INTERVAL = 240  # seconds between keepalive pings (4 min)
AGENCY_NAME  = 'WOR'      # which agency to hold under

# Time slots to prioritize (hold these first)
PRIORITY_TIMES = ['08:00', '08:30', '09:00', '09:30', '10:00',
                  '10:30', '11:00', '11:30', '12:00', '14:00',
                  '14:30', '15:00', '15:30', '16:00', '17:00', '17:30']


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def get_all_dates():
    """All dates from START_DATE to END_DATE, excluding Sundays."""
    dates = []
    d = START_DATE
    while d <= END_DATE:
        if d.weekday() != 6:  # skip Sunday
            dates.append(d.strftime('%d/%m/%Y'))
        d += timedelta(days=1)
    return dates


def scan_available_slots(visitors=VISITORS):
    """Scan all May/June dates and return available slots."""
    s = requests.Session()
    available = []
    dates = get_all_dates()
    log(f"Scanning {len(dates)} dates for {visitors} visitors...")

    for date_str in dates:
        try:
            r = s.get(f'{BASE}/api/search/resultPerTag', params={
                'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date_str,
                'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
            }, headers=H, timeout=8)
            if r.status_code != 200:
                continue

            visits = r.json().get('visits', [])
            ticket = next((v for v in visits
                           if 'musei vaticani' in v.get('name', '').lower()
                           and 'ingresso' in v.get('name', '').lower()
                           and v.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')), None)
            if not ticket:
                sys.stdout.write(f"\r  {date_str} — no ticket")
                sys.stdout.flush()
                continue

            tid = str(ticket['id'])
            r2 = s.get(f'{BASE}/api/visit/timeavail', params={
                'lang': 'it', 'visitLang': '', 'visitTypeId': tid,
                'visitorNum': str(visitors), 'visitDate': date_str,
            }, headers=H, timeout=8)
            if r2.status_code != 200:
                continue

            slots = [sl for sl in r2.json().get('timetable', [])
                     if sl.get('availability') == 'AVAILABLE']
            if slots:
                sys.stdout.write(f"\r  {date_str} — {len(slots)} slots ✅\n")
                sys.stdout.flush()
                for sl in slots:
                    available.append({
                        'date': date_str,
                        'slot_id': str(sl['id']),
                        'slot_time': sl['time'],
                        'ticket_id': tid,
                        'ticket_name': ticket.get('name', 'Musei Vaticani'),
                        'visitors': visitors,
                    })
            else:
                sys.stdout.write(f"\r  {date_str} — sold out")
                sys.stdout.flush()

            time.sleep(0.2)
        except Exception as e:
            log(f"  Error {date_str}: {e}")

    print()
    return available


def hold_all_slots(visitors=VISITORS, dry_run=False):
    """Hold all available May/June slots."""
    try:
        agency = Agency.objects.get(name=AGENCY_NAME)
    except Agency.DoesNotExist:
        log(f"❌ Agency '{AGENCY_NAME}' not found")
        return

    # Get or create a monitor task for pre-holds
    task, _ = MonitorTask.objects.get_or_create(
        agency=agency,
        area_name='Musei Vaticani - Biglietti d\'ingresso',
        defaults={
            'site': 'vatican',
            'dates': [],
            'preferred_times': PRIORITY_TIMES,
            'visitors': visitors,
            'adult_count': visitors,
            'child_count': 0,
            'tier': 'hold',
            'is_active': True,
        }
    )

    available = scan_available_slots(visitors)
    log(f"\nFound {len(available)} available slots across May/June")

    if dry_run:
        log("DRY RUN — not holding")
        for s in available[:20]:
            log(f"  {s['date']} {s['slot_time']} | slot_id={s['slot_id']}")
        return

    # Sort by priority times first
    def sort_key(s):
        t = s['slot_time']
        try: return PRIORITY_TIMES.index(t)
        except ValueError: return 99

    available.sort(key=sort_key)

    held_count = 0
    failed_count = 0

    for slot in available:
        # Skip if already held
        existing = HeldSlot.objects.filter(
            task__agency=agency,
            date=slot['date'],
            slot_time=slot['slot_time'],
            status__in=['held', 'paying']
        ).first()
        if existing:
            log(f"  ⏭️  Already held: {slot['date']} {slot['slot_time']}")
            continue

        log(f"  🔒 Holding {slot['date']} {slot['slot_time']} ({visitors}v)...")
        held = hold_slot(
            task=task,
            date=slot['date'],
            slot_id=slot['slot_id'],
            slot_time=slot['slot_time'],
            ticket_id=slot['ticket_id'],
            ticket_name=slot['ticket_name'],
            visitors=visitors,
        )
        if held:
            log(f"  ✅ Held #{held.id} | recapId={held.recap_id} | €{held.total_price}")
            held_count += 1
        else:
            log(f"  ❌ Failed to hold {slot['date']} {slot['slot_time']}")
            failed_count += 1

        time.sleep(1)  # be gentle with Vatican API

    log(f"\n✅ Held: {held_count} | ❌ Failed: {failed_count}")


def run_keepalive_loop():
    """
    Continuously keepalive all held slots.
    Pings every KEEPALIVE_INTERVAL seconds.
    Run this in a separate terminal to keep holds alive.
    """
    log(f"🔄 Keepalive loop started (interval={KEEPALIVE_INTERVAL}s)")
    while True:
        try:
            held_slots = HeldSlot.objects.filter(
                status='held',
                task__agency__name=AGENCY_NAME
            ).order_by('last_keepalive_at')

            if not held_slots.exists():
                log("  No held slots to keepalive")
            else:
                log(f"  Keepalive for {held_slots.count()} slots...")
                for hs in held_slots:
                    ok = keepalive_slot(hs)
                    status = "✅" if ok else "❌"
                    log(f"  {status} Hold #{hs.id} | {hs.date} {hs.slot_time} | recapId={hs.recap_id}")
                    time.sleep(0.5)

        except Exception as e:
            log(f"  Keepalive error: {e}")

        log(f"  Next keepalive in {KEEPALIVE_INTERVAL}s...")
        time.sleep(KEEPALIVE_INTERVAL)


def show_status():
    """Show all currently held slots."""
    slots = HeldSlot.objects.filter(
        task__agency__name=AGENCY_NAME,
        status__in=['held', 'paying']
    ).order_by('date', 'slot_time')

    print(f"\n{'='*70}")
    print(f"  HELD SLOTS — {AGENCY_NAME}")
    print(f"{'='*70}")
    if not slots.exists():
        print("  No held slots")
    else:
        for hs in slots:
            age = int((timezone.now() - hs.hold_started_at).total_seconds() / 60)
            last_ka = int((timezone.now() - hs.last_keepalive_at).total_seconds() / 60)
            print(f"  #{hs.id:4d} | {hs.date} {hs.slot_time} | {hs.visitors}v | "
                  f"€{hs.total_price} | age={age}m | last_ka={last_ka}m | recapId={hs.recap_id}")
    print(f"{'='*70}\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--scan',      action='store_true', help='Scan available slots')
    parser.add_argument('--hold',      action='store_true', help='Hold all available slots')
    parser.add_argument('--keepalive', action='store_true', help='Run keepalive loop')
    parser.add_argument('--status',    action='store_true', help='Show held slots')
    parser.add_argument('--dry-run',   action='store_true', help='Scan only, no holding')
    parser.add_argument('--visitors',  type=int, default=VISITORS)
    args = parser.parse_args()

    if args.scan:
        slots = scan_available_slots(args.visitors)
        print(f"\nTotal available: {len(slots)}")
        for s in slots:
            print(f"  {s['date']} {s['slot_time']} | {s['visitors']}v")

    elif args.hold:
        hold_all_slots(args.visitors, dry_run=args.dry_run)

    elif args.keepalive:
        run_keepalive_loop()

    elif args.status:
        show_status()

    else:
        parser.print_help()
