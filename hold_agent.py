"""
Vatican Distributed Hold Agent
================================
Runs on ANY device: Windows, Linux, Android (Termux), Raspberry Pi.
No browser needed — pure HTTP recap calls to hold Vatican slots.

Each device running this script can hold 10-30 slots simultaneously.
Run 10 devices = 100-300 simultaneous holds.

How it works:
  1. Polls your Docker server for available slots (timeavail API)
  2. Claims a slot (marks it as owned by this agent)
  3. Calls Vatican /api/visit/recap to lock the slot
  4. Sends heartbeat recap every 4 minutes to keep it locked
  5. Reports hold status back to server + Telegram

Setup (any device):
  pip install requests

Android (Termux):
  pkg install python
  pip install requests
  python hold_agent.py --server https://hydrabot.it --agent android-1

Windows:
  python hold_agent.py --server https://hydrabot.it --agent windows-pc

Run multiple agents on same machine (different slots):
  python hold_agent.py --agent pc-1 --max-holds 5
  python hold_agent.py --agent pc-2 --max-holds 5
"""
import argparse
import json
import logging
import os
import platform
import socket
import sys
import time
import threading
import uuid
from datetime import datetime

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('hold-agent')

# ── CONFIG (override via CLI args or env vars) ────────────────────────────────
SERVER_URL       = os.getenv('SERVER_URL', 'https://hydrabot.it')
BOT_TOKEN        = os.getenv('BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
POLL_INTERVAL    = int(os.getenv('POLL_INTERVAL', '10'))       # seconds between slot checks
HEARTBEAT_SECS   = int(os.getenv('HEARTBEAT_SECS', '240'))     # 4 minutes
MAX_HOLDS        = int(os.getenv('MAX_HOLDS', '10'))            # max simultaneous holds per agent
AGENT_ID         = os.getenv('AGENT_ID', f"{platform.node()}-{uuid.uuid4().hex[:6]}")

BASE = 'https://tickets.museivaticani.va'
HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': f'{BASE}/',
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}
# ─────────────────────────────────────────────────────────────────────────────


def send_telegram(msg: str):
    try:
        requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
            json={'chat_id': TELEGRAM_CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'},
            timeout=5
        )
    except Exception:
        pass


def get_profile() -> dict:
    """Fetch buyer profile from server."""
    try:
        r = requests.get(f'{SERVER_URL}/api/v1/buyer-profile/', timeout=8)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {'first_name': 'Mario', 'last_name': 'Rossi', 'email': 'mario@example.com',
            'phone': '3401234567', 'city': 'Roma', 'country': 'Italy'}


def get_pending_jobs() -> list:
    """
    Poll server for slots that need holding.
    Returns list of job dicts from browser_pending queue.
    """
    try:
        r = requests.get(f'{SERVER_URL}/api/v1/browser-pending/', timeout=8)
        if r.status_code == 200:
            return r.json().get('requests', [])
    except Exception:
        pass
    return []


def get_held_slots() -> list:
    """Get all currently held slots from server."""
    try:
        r = requests.get(f'{SERVER_URL}/api/v1/holds/?status=held', timeout=8)
        if r.status_code == 200:
            return r.json().get('results', [])
    except Exception:
        pass
    return []


def pause_recap_on_server(hold_id):
    try:
        requests.post(f'{SERVER_URL}/api/v1/holds/{hold_id}/pause-recap/', timeout=5)
    except Exception:
        pass


def resume_recap_on_server(hold_id):
    try:
        requests.post(f'{SERVER_URL}/api/v1/holds/{hold_id}/resume-recap/', timeout=5)
    except Exception:
        pass


def mark_paid_on_server(hold_id, reference='', epay_url=''):
    try:
        requests.post(f'{SERVER_URL}/api/v1/mark-paid/', json={
            'hold_id': hold_id, 'reference': reference, 'epay_url': epay_url
        }, timeout=5)
    except Exception:
        pass


# ── Vatican API calls ─────────────────────────────────────────────────────────

def get_fresh_session(date: str, visitors: int) -> tuple:
    """
    Call Search API to get fresh JSESSIONID + ticket_id.
    Returns (session, ticket_id) or (None, None) on failure.
    """
    s = requests.Session()
    try:
        # Warm up
        s.get(f'{BASE}/home', headers={'User-Agent': HEADERS['User-Agent']}, timeout=10)
    except Exception:
        pass

    try:
        r = s.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date,
            'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
        }, headers=HEADERS, timeout=10)

        if r.status_code != 200:
            logger.warning(f"Search API {r.status_code} for {date}")
            return None, None

        visits = r.json().get('visits', [])
        ticket = next((v for v in visits
                       if 'musei vaticani' in v.get('name', '').lower()
                       and 'ingresso' in v.get('name', '').lower()), None)
        if not ticket:
            logger.warning(f"No standard entry ticket for {date}")
            return None, None

        return s, str(ticket['id'])
    except Exception as e:
        logger.error(f"get_fresh_session error: {e}")
        return None, None


def get_available_slots(date: str, visitors: int, session=None, ticket_id=None) -> list:
    """Call timeavail API and return available slots."""
    if not session or not ticket_id:
        session, ticket_id = get_fresh_session(date, visitors)
    if not session:
        return []

    try:
        r = session.get(f'{BASE}/api/visit/timeavail', params={
            'lang': 'it', 'visitLang': '', 'visitTypeId': ticket_id,
            'visitorNum': str(visitors), 'visitDate': date,
        }, headers=HEADERS, timeout=10)

        if r.status_code != 200:
            return []

        return [s for s in r.json().get('timetable', [])
                if s.get('availability') in ('AVAILABLE', 'LOW_AVAILABILITY')]
    except Exception as e:
        logger.error(f"timeavail error: {e}")
        return []


def do_recap(session, slot_id: str, ticket_id: str, visitors: int,
             adult_count: int, child_count: int) -> str | None:
    """
    Call /api/visit/recap to lock a slot.
    Returns recap_id on success, None on failure.
    """
    body = {
        "visitId": str(slot_id),
        "visitTypeId": int(ticket_id),
        "visitorNum": int(visitors),
        "lang": "it",
        "tickets": [
            {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(adult_count)},
            {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": str(child_count)},
        ],
        "additionalCosts": {
            "service-0": {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(visitors)}
        },
        "services": [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(visitors)}]
    }
    try:
        r = session.post(f'{BASE}/api/visit/recap', json=body, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return data.get('recapId') or data.get('id') or 'ok'
        logger.warning(f"Recap {r.status_code}: {r.text[:100]}")
    except Exception as e:
        logger.error(f"Recap error: {e}")
    return None


# ── Hold worker (one thread per held slot) ────────────────────────────────────

class HoldWorker(threading.Thread):
    """
    Holds one Vatican slot indefinitely via recap heartbeat.
    Runs in its own thread so multiple slots can be held in parallel.
    """

    def __init__(self, slot_info: dict, profile: dict, agent_id: str):
        super().__init__(daemon=True)
        self.slot = slot_info
        self.profile = profile
        self.agent_id = agent_id
        self.running = True
        self.held = False
        self.recap_id = None
        self.session = None
        self.ticket_id = None

        self.date = slot_info.get('date', '')
        self.slot_time = slot_info.get('slot_time', '')
        self.slot_id = str(slot_info.get('slot_id', ''))
        self.visitors = int(slot_info.get('visitors', 1))
        self.adult_count = int(slot_info.get('adult_count', self.visitors))
        self.child_count = int(slot_info.get('child_count', 0))
        self.hold_id = slot_info.get('id')  # server-side HeldSlot ID
        self.label = f"[{self.date} {self.slot_time}]"

    def log(self, msg):
        logger.info(f"{self.label} {msg}")

    def run(self):
        self.log(f"Starting hold worker (agent={self.agent_id})")

        # Get fresh session + ticket_id
        self.session, self.ticket_id = get_fresh_session(self.date, self.visitors)
        if not self.session:
            self.log("❌ Could not get Vatican session — aborting")
            return

        # If slot_id not provided, find an available slot
        if not self.slot_id:
            slots = get_available_slots(self.date, self.visitors, self.session, self.ticket_id)
            if not slots:
                self.log(f"❌ No available slots for {self.date}")
                return
            best = slots[0]
            self.slot_id = str(best['id'])
            self.slot_time = best['time']
            self.log(f"Found slot: {self.slot_time} (id={self.slot_id})")

        # Initial recap — lock the slot
        self.log(f"Calling recap for slot_id={self.slot_id}...")
        self.recap_id = do_recap(
            self.session, self.slot_id, self.ticket_id,
            self.visitors, self.adult_count, self.child_count
        )

        if not self.recap_id:
            self.log("❌ Initial recap failed — slot may be taken")
            return

        self.held = True
        self.log(f"✅ HELD! recap_id={self.recap_id}")
        send_telegram(
            f"🔒 *Slot held by {self.agent_id}*\n"
            f"📅 {self.date} {self.slot_time} | 👥 {self.visitors}v\n"
            f"Heartbeat every {HEARTBEAT_SECS}s"
        )

        # Heartbeat loop
        last_heartbeat = time.time()
        while self.running:
            time.sleep(5)
            elapsed = time.time() - last_heartbeat

            if elapsed >= HEARTBEAT_SECS:
                # Refresh ticket_id (Vatican changes IDs)
                _, fresh_tid = get_fresh_session(self.date, self.visitors)
                if fresh_tid:
                    self.ticket_id = fresh_tid

                recap_id = do_recap(
                    self.session, self.slot_id, self.ticket_id,
                    self.visitors, self.adult_count, self.child_count
                )
                if recap_id:
                    self.recap_id = recap_id
                    last_heartbeat = time.time()
                    self.log(f"💓 Heartbeat OK")
                else:
                    self.log(f"⚠️ Heartbeat failed — refreshing session...")
                    self.session, self.ticket_id = get_fresh_session(self.date, self.visitors)
                    if not self.session:
                        self.log("❌ Session refresh failed — hold lost")
                        self.held = False
                        send_telegram(f"❌ Hold lost: {self.date} {self.slot_time} (session expired)")
                        break
                    last_heartbeat = time.time()

        self.log("Hold worker stopped")

    def stop(self):
        self.running = False


# ── Main agent loop ───────────────────────────────────────────────────────────

class DistributedHoldAgent:
    """
    Polls the Docker server for slots to hold.
    Spawns a HoldWorker thread for each slot.
    Supports up to MAX_HOLDS simultaneous holds.
    """

    def __init__(self, agent_id: str, max_holds: int, server_url: str,
                 dates: list = None, visitors: int = 2):
        self.agent_id = agent_id
        self.max_holds = max_holds
        self.server_url = server_url
        self.target_dates = dates or []
        self.visitors = visitors
        self.workers: dict[str, HoldWorker] = {}  # slot_key → worker
        self.profile = get_profile()
        logger.info(f"Agent {agent_id} | max_holds={max_holds} | profile={self.profile.get('first_name')} {self.profile.get('last_name')}")

    def active_holds(self) -> int:
        return sum(1 for w in self.workers.values() if w.is_alive() and w.held)

    def cleanup_dead_workers(self):
        dead = [k for k, w in self.workers.items() if not w.is_alive()]
        for k in dead:
            del self.workers[k]

    def hold_slot(self, slot_info: dict):
        """Spawn a worker to hold this slot."""
        key = f"{slot_info.get('date')}_{slot_info.get('slot_time')}_{slot_info.get('slot_id','')}"
        if key in self.workers:
            return  # already holding

        worker = HoldWorker(slot_info, self.profile, self.agent_id)
        self.workers[key] = worker
        worker.start()
        logger.info(f"Spawned worker for {slot_info.get('date')} {slot_info.get('slot_time')}")

    def scan_and_hold(self):
        """
        Scan target dates for available slots and hold them.
        Used when running in standalone mode (not server-driven).
        """
        if not self.target_dates:
            return

        for date in self.target_dates:
            if self.active_holds() >= self.max_holds:
                logger.info(f"At max holds ({self.max_holds}) — skipping scan")
                break

            session, ticket_id = get_fresh_session(date, self.visitors)
            if not session:
                continue

            slots = get_available_slots(date, self.visitors, session, ticket_id)
            logger.info(f"{date}: {len(slots)} available slots")

            for slot in slots:
                if self.active_holds() >= self.max_holds:
                    break
                slot_info = {
                    'date': date,
                    'slot_time': slot['time'],
                    'slot_id': str(slot['id']),
                    'visitors': self.visitors,
                    'adult_count': self.visitors,
                    'child_count': 0,
                    'id': None,  # no server-side hold ID in standalone mode
                }
                self.hold_slot(slot_info)
                time.sleep(0.5)  # stagger

    def process_server_jobs(self):
        """Process jobs from the Docker server's browser_pending queue."""
        jobs = get_pending_jobs()
        for job in jobs:
            if self.active_holds() >= self.max_holds:
                logger.info(f"At max holds — skipping job")
                break

            data = job.get('data', '')
            if not data.startswith('open_browser:'):
                continue

            parts = data.split(':')
            hold_id = parts[1] if len(parts) > 1 else None
            if not hold_id:
                continue

            # Decode embedded slot info
            slot_info = {'id': hold_id, 'visitors': self.visitors}
            if len(parts) >= 3:
                try:
                    import base64
                    raw = base64.b64decode(parts[2]).decode()
                    s = raw.split('|')
                    slot_info.update({
                        'date': s[0],
                        'slot_time': s[1],
                        'slot_id': s[2] if len(s) > 2 else '',
                        'visitors': int(s[3]) if len(s) > 3 else self.visitors,
                        'adult_count': int(s[3]) if len(s) > 3 else self.visitors,
                        'child_count': 0,
                    })
                except Exception as e:
                    logger.warning(f"Could not decode job: {e}")

            logger.info(f"Server job: hold #{hold_id} — {slot_info.get('date')} {slot_info.get('slot_time')}")
            self.hold_slot(slot_info)

    def run(self):
        logger.info(f"🚀 Distributed Hold Agent started")
        logger.info(f"   Agent ID : {self.agent_id}")
        logger.info(f"   Server   : {self.server_url}")
        logger.info(f"   Max holds: {self.max_holds}")
        logger.info(f"   Dates    : {self.target_dates or 'from server'}")
        logger.info(f"   Visitors : {self.visitors}")
        logger.info(f"   Poll     : every {POLL_INTERVAL}s\n")

        send_telegram(
            f"🤖 *Hold Agent started*\n"
            f"ID: `{self.agent_id}`\n"
            f"Max holds: {self.max_holds}\n"
            f"Dates: {', '.join(self.target_dates) if self.target_dates else 'server-driven'}"
        )

        while True:
            try:
                self.cleanup_dead_workers()
                active = self.active_holds()
                total = len(self.workers)
                logger.info(f"Status: {active} active holds / {total} workers / {self.max_holds} max")

                # Process server jobs (Docker timeavail monitor found slots)
                self.process_server_jobs()

                # Standalone scan if dates provided
                if self.target_dates and active < self.max_holds:
                    self.scan_and_hold()

            except KeyboardInterrupt:
                logger.info("Stopping agent...")
                for w in self.workers.values():
                    w.stop()
                break
            except Exception as e:
                logger.error(f"Agent loop error: {e}")

            time.sleep(POLL_INTERVAL)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Vatican Distributed Hold Agent')
    parser.add_argument('--server',    default=SERVER_URL,  help='Docker server URL (default: %(default)s)')
    parser.add_argument('--agent',     default=AGENT_ID,    help='Unique agent ID (default: hostname-random)')
    parser.add_argument('--max-holds', type=int, default=MAX_HOLDS, help='Max simultaneous holds (default: %(default)s)')
    parser.add_argument('--visitors',  type=int, default=2,  help='Visitors per ticket (default: %(default)s)')
    parser.add_argument('--dates',     nargs='+',            help='Dates to scan DD/MM/YYYY (optional — uses server if omitted)')
    parser.add_argument('--chat-id',   default=TELEGRAM_CHAT_ID, help='Telegram chat ID for notifications')
    parser.add_argument('--token',     default=BOT_TOKEN,   help='Telegram bot token')
    args = parser.parse_args()

    # Apply CLI overrides
    SERVER_URL       = args.server
    AGENT_ID         = args.agent
    MAX_HOLDS        = args.max_holds
    TELEGRAM_CHAT_ID = args.chat_id
    BOT_TOKEN        = args.token

    agent = DistributedHoldAgent(
        agent_id=args.agent,
        max_holds=args.max_holds,
        server_url=args.server,
        dates=args.dates or [],
        visitors=args.visitors,
    )

    # Watchdog restart on crash
    while True:
        try:
            agent.run()
            break
        except KeyboardInterrupt:
            logger.info("Agent stopped.")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Agent crashed: {e} — restarting in 15s...")
            time.sleep(15)
