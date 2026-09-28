"""Local web dashboard server.

Serves a single-page dashboard on localhost and a small JSON API that the page
uses to manage config, connect sheets, map columns, add proxies, and start/stop
the booking run. Stdlib-only (http.server) so it packs cleanly with PyInstaller.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import AppConfig, ProxyConfig, SheetConfig, default_config, load_config, save_config
from .orchestrator import Orchestrator
from .providers import default_registry
from .proxies import Proxy, ProxyPool
from .sheets import connect_sheet, extract_sheet_id, rows_to_targets
from .watcher import Watcher, WatchTarget

log = logging.getLogger("sniper")

HOST = "127.0.0.1"
PORT = int(os.getenv("VATICAN_DASHBOARD_PORT", "8765"))
HTML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")

_state: dict = {
    "config": None,
    "orchestrator": None,
    "run_thread": None,
    "watcher": None,
}


def _get_watcher() -> Watcher:
    if _state["watcher"] is None:
        _state["watcher"] = Watcher(_get_config())
    return _state["watcher"]


def _get_config() -> AppConfig:
    if _state["config"] is None:
        _state["config"] = load_config()
    return _state["config"]


def _json_body(handler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def _send_json(handler, obj, status=200):
    body = json.dumps(obj).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _send_html(handler):
    try:
        with open(HTML_FILE, "r", encoding="utf-8") as f:
            body = f.read().encode("utf-8")
    except FileNotFoundError:
        body = b"dashboard.html not found"
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter logs
        log.debug(fmt, *args)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            _send_html(self)
        elif self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        elif self.path == "/api/config":
            _send_json(self, _get_config().to_dict())
        elif self.path == "/api/status":
            _send_json(self, _status())
        elif self.path == "/api/credentials/status":
            _send_json(self, _credentials_status())
        elif self.path == "/api/watch":
            _send_json(self, {"watches": [w.to_dict() for w in _get_watcher().list()]})
        elif self.path == "/api/health":
            _send_json(self, {"ok": True})
        else:
            _send_json(self, {"error": "not found"}, 404)

    def do_POST(self):
        try:
            self._route_post()
        except FileNotFoundError as e:
            _send_json(self, {
                "error": (f"Couldn't find the Google credentials file ({e}). "
                          "Put google_credentials.json in ~/.vatican-sniper/ (or ~/Downloads/) "
                          "and set Settings → service account file to 'google_credentials.json'."),
            }, 400)
        except PermissionError:
            _send_json(self, {
                "error": ("No access to that sheet. Share it (Editor) with the "
                          "service-account email inside google_credentials.json."),
            }, 403)
        except Exception as e:  # noqa: BLE001
            log.exception("request failed")
            _send_json(self, {"error": str(e)}, 500)

    def _route_post(self):
        path = self.path.split("?")[0]
        if path == "/api/config":
            self._save_config()
        elif path == "/api/connect":
            self._connect()
        elif path == "/api/preview":
            self._preview()
        elif path == "/api/proxies/test":
            self._test_proxy()
        elif path == "/api/run":
            self._run()
        elif path == "/api/stop":
            self._stop()
        elif path == "/api/watch/add":
            self._watch_add()
        elif path == "/api/watch/add-multi":
            self._watch_add_multi()
        elif path == "/api/watch/remove":
            self._watch_remove()
        else:
            _send_json(self, {"error": "not found"}, 404)

    def _save_config(self):
        data = _json_body(self)
        cfg = AppConfig.from_dict(data)
        path = save_config(cfg)
        _state["config"] = cfg
        _send_json(self, {"ok": True, "path": path})

    def _connect(self):
        data = _json_body(self)
        cfg = _get_config()
        result = connect_sheet(
            data.get("url", ""),
            cfg.google.service_account_file,
            tab=data.get("tab", ""),
        )
        _send_json(self, result)

    def _preview(self):
        data = _json_body(self)
        cfg = _get_config()
        scfg = SheetConfig.from_dict(data.get("sheet", {}))
        # Read raw rows then map, so the user sees what would be booked.
        from .sheets import _authorize
        client = _authorize(cfg.google.service_account_file)
        sheet = client.open_by_key(scfg.sheet_id)
        ws = sheet.worksheet(scfg.tab) if scfg.tab else sheet.sheet1
        records = ws.get_all_records()
        targets = rows_to_targets(records, scfg, default_visitors=cfg.booking.default_visitors)
        _send_json(self, {
            "total_rows": len(records),
            "matched": len(targets),
            "bookings": [
                {
                    "booking_id": t.booking_id,
                    "activity_date": t.activity_date,
                    "visitors": t.visitors,
                    "customer_name": t.customer_name,
                    "customer_email": t.customer_email,
                    "product_title": t.product_title,
                    "status": t.status,
                }
                for t in targets[:50]
            ],
        })

    def _test_proxy(self):
        data = _json_body(self)
        p = Proxy(
            host=data.get("host", ""),
            port=int(data.get("port", 8080)),
            username=data.get("username", ""),
            password=data.get("password", ""),
        )
        _send_json(self, ProxyPool([]).test(p))

    def _run(self):
        if _state["run_thread"] and _state["run_thread"].is_alive():
            _send_json(self, {"error": "already running"}, 409)
            return
        cfg = _get_config()
        orch = Orchestrator(cfg)
        _state["orchestrator"] = orch
        t = threading.Thread(target=orch.run, daemon=True)
        _state["run_thread"] = t
        t.start()
        _send_json(self, {"ok": True, "state": "running"})

    def _stop(self):
        orch = _state["orchestrator"]
        if orch is not None:
            orch.stop()
        _send_json(self, {"ok": True, "state": "stopped"})

    def _watch_add(self):
        data = _json_body(self)
        w = WatchTarget(
            date=data.get("date", ""),
            time=data.get("time", ""),
            visitors=int(data.get("visitors", 2)),
            name=data.get("name", ""),
            email=data.get("email", ""),
        )
        if not w.date or not w.time:
            _send_json(self, {"error": "date and time are required"}, 400)
            return
        _get_watcher().add(w)
        _send_json(self, {"ok": True, "watch": w.to_dict()})

    def _watch_add_multi(self):
        data = _json_body(self)
        date = data.get("date", "")
        times = [t for t in (data.get("times") or []) if t]
        visitors = int(data.get("visitors", 2))
        name = data.get("name", "")
        email = data.get("email", "")
        groups = int(data.get("groups", 1))
        if not date or not times:
            _send_json(self, {"error": "date and at least one time are required"}, 400)
            return
        watches = _get_watcher().add_multi(date, times, visitors, name, email, groups)
        _send_json(self, {"ok": True, "added": len(watches),
                          "watches": [w.to_dict() for w in watches]})

    def _watch_remove(self):
        data = _json_body(self)
        ok = _get_watcher().remove(data.get("id", ""))
        _send_json(self, {"ok": ok})


def _status() -> dict:
    orch = _state["orchestrator"]
    cfg = _get_config()
    return {
        "state": orch.state if orch else "idle",
        "status": orch.status if orch else {},
        "providers": [p.venue_id for p in default_registry().all()],
        "sheets": len(cfg.sheets),
        "proxies": len(cfg.proxies),
    }


def _credentials_status() -> dict:
    from .sheets import _resolve_path

    cfg = _get_config()
    configured = cfg.google.service_account_file or "google_credentials.json"
    resolved = _resolve_path(configured)
    found = bool(resolved) and os.path.exists(resolved)
    suggested = os.path.join(os.path.expanduser("~"), ".vatican-sniper", "google_credentials.json")
    return {
        "configured": configured,
        "resolved": resolved,
        "found": found,
        "suggested_path": suggested,
    }


def main(open_browser: bool = True, host: str = HOST, port: int = PORT) -> None:
    from .bootstrap import ensure_config, setup_logging
    from .telemetry import heartbeat_loop, machine_info, send_alert
    import desktop_app

    setup_logging()
    _state["config"] = ensure_config()
    cfg = _state["config"]

    if cfg.telemetry.notify_startup:
        threading.Thread(
            target=send_alert,
            args=(cfg, f"🟢 started v{desktop_app.__version__} — {machine_info()}"),
            daemon=True,
        ).start()
    heartbeat_loop(cfg)

    url = f"http://{host}:{port}"
    try:
        server = ThreadingHTTPServer((host, port), Handler)
    except OSError as e:
        # Port already in use → the app is almost certainly already running.
        # Just open the existing dashboard instead of crashing silently.
        log.warning(f"Port {port} already in use ({e}) — opening existing dashboard.")
        if open_browser:
            webbrowser.open(url)
        return
    log.info(f"Dashboard running at {url}")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
