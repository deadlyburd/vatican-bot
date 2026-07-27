"""
Turnstile Token Pool — warm pool for instant snipe.

Keeps a rolling pool of fresh tokens (~5 at a time).
Tokens expire in ~2 min, so we refresh continuously.
When a snipe fires, grab a token instantly (0s wait).

Usage:
    from monitors.turnstile_pool import get_token_sync, return_unused_token, pool_size
    token = get_token_sync()   # instant if pool is warm, ~30s if cold
"""
import logging
import os
import time
import threading
import requests
from collections import deque

logger = logging.getLogger(__name__)

SITE_KEY  = '0x4AAAAAAB2Edz1zEK7o5Rj1'
PAGE_URL  = 'https://tickets.museivaticani.va/home/checkout'
TOKEN_TTL = 100          # seconds — discard tokens older than this (Turnstile ~2min)
POOL_TARGET = 5          # keep this many fresh tokens ready
POOL_MAX    = 10         # never store more than this
REFILL_INTERVAL = 5      # seconds between pool checks


# ── In-process pool (works within one Celery worker process) ─────────────────
# Each entry: {'token': str, 'solved_at': float}
_pool: deque = deque()
_pool_lock = threading.Lock()
_refill_thread: threading.Thread | None = None
_refill_running = False


def _solve_one_token(api_key: str) -> str | None:
    """Solve a single Turnstile token via 2captcha. Returns token or None."""
    try:
        r = requests.post('https://2captcha.com/in.php', data={
            'key': api_key,
            'method': 'turnstile',
            'sitekey': SITE_KEY,
            'pageurl': PAGE_URL,
            'action': 'managed',
            'json': 1,
        }, timeout=10)
        data = r.json()
        if data.get('status') != 1:
            logger.error(f"2captcha submit failed: {data}")
            return None

        task_id = data['request']

        for _ in range(24):  # up to 2 min
            time.sleep(5)
            r2 = requests.get('https://2captcha.com/res.php', params={
                'key': api_key, 'action': 'get', 'id': task_id, 'json': 1
            }, timeout=10)
            res = r2.json()
            if res.get('status') == 1:
                logger.debug(f"✅ Turnstile solved (task {task_id})")
                return res['request']
            if res.get('request') != 'CAPCHA_NOT_READY':
                logger.error(f"2captcha error: {res}")
                return None

        logger.error("2captcha timeout")
        return None
    except Exception as e:
        logger.error(f"Turnstile solve exception: {e}")
        return None


def _evict_expired():
    """Remove tokens older than TOKEN_TTL from the pool."""
    now = time.time()
    with _pool_lock:
        while _pool and (now - _pool[0]['solved_at']) > TOKEN_TTL:
            old = _pool.popleft()
            logger.debug(f"Evicted expired token (age {now - old['solved_at']:.0f}s)")


def _refill_loop():
    """Background thread — keeps pool topped up."""
    global _refill_running
    api_key = os.getenv('TWOCAPTCHA_API_KEY')
    if not api_key:
        logger.warning("No TWOCAPTCHA_API_KEY — token pool disabled")
        _refill_running = False
        return

    logger.info(f"🔐 Token pool refill thread started (target={POOL_TARGET})")
    while _refill_running:
        try:
            _evict_expired()
            with _pool_lock:
                current = len(_pool)

            if current < POOL_TARGET:
                needed = POOL_TARGET - current
                logger.debug(f"Pool has {current}/{POOL_TARGET} tokens — solving {needed} more")
                for _ in range(needed):
                    if not _refill_running:
                        break
                    token = _solve_one_token(api_key)
                    if token:
                        with _pool_lock:
                            if len(_pool) < POOL_MAX:
                                _pool.append({'token': token, 'solved_at': time.time()})
                                logger.info(f"🔐 Token added to pool (size={len(_pool)})")
            else:
                logger.debug(f"Pool full ({current}/{POOL_TARGET})")

        except Exception as e:
            logger.error(f"Refill loop error: {e}")

        time.sleep(REFILL_INTERVAL)

    logger.info("Token pool refill thread stopped")


def start_pool(force=False):
    """Start the background refill thread. Safe to call multiple times."""
    global _refill_thread, _refill_running
    if _refill_running and not force:
        return
    
    api_key = os.getenv('TWOCAPTCHA_API_KEY')
    if not api_key:
        logger.info("No TWOCAPTCHA_API_KEY — token pool disabled")
        return
    
    # ✅ FIX BUG #8: Check balance before starting pool
    try:
        r = requests.get('https://2captcha.com/res.php', params={
            'key': api_key, 'action': 'getbalance', 'json': 1
        }, timeout=5)
        balance_str = r.json().get('request', '0')
        try:
            balance = float(balance_str)
        except (ValueError, TypeError):
            balance = 0.0
        
        if balance < 0.01:
            logger.warning(f"⚠️ 2captcha balance too low (${balance:.3f}) — token pool disabled")
            logger.warning(f"   Top up at https://2captcha.com to enable auto-booking features")
            return
        
        logger.info(f"✅ 2captcha balance: ${balance:.2f} — starting token pool")
    except Exception as e:
        logger.error(f"Failed to check 2captcha balance: {e}")
        logger.warning("Token pool disabled due to balance check failure")
        return
    
    _refill_running = True
    _refill_thread = threading.Thread(target=_refill_loop, daemon=True, name='turnstile-pool')
    _refill_thread.start()
    logger.info("🔐 Token pool started")


def stop_pool():
    global _refill_running
    _refill_running = False


def get_token_sync() -> str | None:
    """
    Get a fresh Turnstile token.
    - If pool has a fresh token: returns instantly (0s)
    - If pool is empty: solves one on-demand (~30s)
    """
    api_key = os.getenv('TWOCAPTCHA_API_KEY')
    if not api_key:
        logger.error("No TWOCAPTCHA_API_KEY set")
        return None

    # Start pool if not running
    start_pool()

    # Try pool first
    _evict_expired()
    with _pool_lock:
        if _pool:
            entry = _pool.popleft()
            age = time.time() - entry['solved_at']
            logger.info(f"⚡ Token from pool (age={age:.0f}s, remaining={len(_pool)})")
            return entry['token']

    # Pool empty — solve on demand
    logger.info("🔐 Pool empty — solving Turnstile on demand (~30s)...")
    return _solve_one_token(api_key)


def return_unused_token(token: str) -> None:
    """Return an unused token back to the pool (e.g. snipe was cancelled)."""
    if not token:
        return
    with _pool_lock:
        if len(_pool) < POOL_MAX:
            _pool.appendleft({'token': token, 'solved_at': time.time()})
            logger.debug(f"Token returned to pool (size={len(_pool)})")


def pool_size() -> int:
    _evict_expired()
    with _pool_lock:
        return len(_pool)
