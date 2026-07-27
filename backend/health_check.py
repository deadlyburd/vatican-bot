import os
import sys
import logging
import socket

# Setup paths and Django
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if BASE_DIR in sys.path:
    sys.path.remove(BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django
django.setup()

import requests
import redis as redis_lib
from celery import Celery
from django.conf import settings
from monitors.models import MonitorTask

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("HealthCheck")


def check_redis():
    broker_url = getattr(settings, "CELERY_BROKER_URL", os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"))
    logger.info(f"Redis broker: {broker_url}")
    try:
        r = redis_lib.from_url(broker_url)
        pong = r.ping()
        return ("Redis", "UP" if pong else "DOWN", broker_url)
    except Exception as e:
        return ("Redis", f"DOWN ({e})", broker_url)


def check_celery_ping():
    try:
        app = Celery()
        app.conf.broker_url = getattr(settings, "CELERY_BROKER_URL", None)
        app.conf.result_backend = getattr(settings, "CELERY_RESULT_BACKEND", None)
        replies = app.control.ping(timeout=2)
        status = "UP" if replies else "NO REPLY"
        return ("Celery Workers", status, str(replies))
    except Exception as e:
        return ("Celery Workers", f"DOWN ({e})", "")


def check_db():
    try:
        count = MonitorTask.objects.count()
        return ("Database", "UP", f"MonitorTask count: {count}")
    except Exception as e:
        return ("Database", f"DOWN ({e})", "")


def check_telegram():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return ("Telegram API", "NO TOKEN", "")
    try:
        resp = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
        ok = resp.status_code == 200 and resp.json().get("ok") is True
        return ("Telegram API", "UP" if ok else f"DOWN ({resp.status_code})", resp.text[:120])
    except Exception as e:
        return ("Telegram API", f"DOWN ({e})", "")


def check_frontend():
    candidates = ["http://localhost:3000", "http://127.0.0.1:3000"]
    for url in candidates:
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code < 500:
                return ("Frontend", "UP", f"{url} -> {resp.status_code}")
        except Exception:
            continue
    return ("Frontend", "DOWN", "No local dev server detected on :3000")


def check_ports():
    # Basic TCP port checks
    to_check = [("redis", "localhost", 6379), ("redis-docker", "redis", 6379)]
    results = []
    for name, host, port in to_check:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        try:
            s.connect((host, port))
            results.append((f"Port {name}", "OPEN", f"{host}:{port}"))
        except Exception as e:
            results.append((f"Port {name}", f"CLOSED ({e.__class__.__name__})", f"{host}:{port}"))
        finally:
            s.close()
    return results


def main():
    checks = []
    checks.append(check_redis())
    checks.append(check_celery_ping())
    checks.append(check_db())
    checks.append(check_telegram())
    checks.append(check_frontend())
    checks.extend(check_ports())

    print("\n" + "=" * 60)
    print("SERVICE HEALTH REPORT")
    print("=" * 60)
    for name, status, info in checks:
        print(f"{name:18} : {status:10} | {info}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

