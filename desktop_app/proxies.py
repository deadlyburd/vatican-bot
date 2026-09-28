"""Proxy pool for the desktop sniper.

Stores proxies, assigns them to bookings (round-robin or sticky-by-date), and
builds the right launch flag for Chrome or a dict for Playwright/requests.

Note: Chrome's --proxy-server cannot send a username/password. For auth proxies
use IP whitelisting in the provider dashboard, or the Playwright proxy dict
(launch_persistent_context(proxy=...)).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Proxy:
    host: str = ""
    port: int = 8080
    username: str = ""
    password: str = ""
    enabled: bool = True
    last_error: str = ""

    def has_auth(self) -> bool:
        return bool(self.username)

    def url(self) -> str:
        auth = f"{self.username}:{self.password}@" if self.username else ""
        return f"http://{auth}{self.host}:{self.port}"

    def requests_proxy(self) -> dict:
        u = self.url()
        return {"http": u, "https": u}

    def chrome_flag(self) -> Optional[str]:
        """--proxy-server flag. Returns None for auth proxies (Chrome CLI can't auth)."""
        if self.has_auth():
            return None
        return f"--proxy-server=http://{self.host}:{self.port}"

    def playwright_proxy(self) -> dict:
        return {
            "server": f"http://{self.host}:{self.port}",
            "username": self.username,
            "password": self.password,
        }


class ProxyPool:
    def __init__(self, proxies: Optional[List[Proxy]] = None):
        self.proxies = list(proxies or [])
        self._rr = 0

    def active(self) -> List[Proxy]:
        return [p for p in self.proxies if p.enabled]

    def round_robin(self) -> Optional[Proxy]:
        active = self.active()
        if not active:
            return None
        p = active[self._rr % len(active)]
        self._rr += 1
        return p

    def sticky_by_date(self, date_key: str) -> Optional[Proxy]:
        """Deterministically map a date to one proxy (stable across restarts)."""
        active = self.active()
        if not active:
            return None
        digest = hashlib.md5(date_key.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % len(active)
        return active[idx]

    def test(self, proxy: Proxy, timeout: int = 10) -> dict:
        """Probe a proxy via an IP-echo service. Never raises."""
        import requests
        try:
            r = requests.get(
                "https://api.ipify.org?format=json",
                proxies=proxy.requests_proxy(),
                timeout=timeout,
            )
            ok = r.status_code == 200
            ip = r.json().get("ip") if ok else None
            return {
                "ok": ok,
                "ip": ip,
                "latency_ms": round(r.elapsed.total_seconds() * 1000),
                "error": "" if ok else f"HTTP {r.status_code}",
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "ip": None, "latency_ms": None, "error": str(e)}
