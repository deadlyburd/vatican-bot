"""
Custom SSL adapter for epay.catholica.va
=========================================
epay.catholica.va uses AES256-GCM-SHA384 (RSA key exchange, no forward secrecy).
OpenSSL 3.0 disables this at SECLEVEL=2 (default), causing handshake failure.

Fix: Use SECLEVEL=1 only for epay.catholica.va, keep SECLEVEL=2 everywhere else.
"""
import ssl
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context


EPAY_HOST = 'epay.catholica.va'

# Cipher string that includes RSA key exchange ciphers (needed by epay.catholica.va)
# SECLEVEL=1 allows RSA key exchange while still requiring TLS 1.2+
EPAY_CIPHERS = 'DEFAULT:@SECLEVEL=1'


class EpaySSLAdapter(HTTPAdapter):
    """
    Custom SSL adapter that uses SECLEVEL=1 ciphers for epay.catholica.va.
    Allows AES256-GCM-SHA384 (RSA key exchange) which epay requires.
    """

    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_ciphers(EPAY_CIPHERS)
        # Force TLS 1.2 minimum (no SSLv3, no TLS 1.0/1.1)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        kwargs['ssl_context'] = ctx
        super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        ctx = create_urllib3_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_ciphers(EPAY_CIPHERS)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        proxy_kwargs['ssl_context'] = ctx
        return super().proxy_manager_for(proxy, **proxy_kwargs)


def make_epay_session(jsessionid=None, ticketmv=None, serverid=None):
    """
    Create a requests.Session pre-configured for epay.catholica.va SSL.
    Mounts the custom adapter for https://epay.catholica.va only.
    Also restores Vatican session cookies if provided.
    """
    s = requests.Session()
    s.mount('https://epay.catholica.va', EpaySSLAdapter())

    if jsessionid:
        s.cookies.set('JSESSIONID', jsessionid, domain='tickets.museivaticani.va')
    if ticketmv:
        s.cookies.set('ticketmv', ticketmv, domain='tickets.museivaticani.va')
    if serverid:
        s.cookies.set('SERVERID', serverid, domain='tickets.museivaticani.va')

    return s


def make_vatican_session(jsessionid=None, ticketmv=None, serverid=None, use_proxy=False):
    """
    Create a requests.Session for tickets.museivaticani.va + epay.catholica.va.
    Mounts the epay adapter so payment redirects work seamlessly.
    Set use_proxy=True to route through a random active proxy (avoids rate limiting).
    """
    s = requests.Session()
    s.mount('https://epay.catholica.va', EpaySSLAdapter())

    if use_proxy:
        try:
            from monitors.models import Proxy
            from django.utils import timezone
            from django.db import models as dm
            now = timezone.now()
            p = Proxy.objects.filter(is_active=True).filter(
                dm.Q(cooldown_until__isnull=True) | dm.Q(cooldown_until__lte=now)
            ).order_by('?').first()
            if p:
                if p.username and p.password:
                    proxy_url = f"http://{p.username}:{p.password}@{p.ip_port}"
                else:
                    proxy_url = f"http://{p.ip_port}"
                s.proxies = {'http': proxy_url, 'https': proxy_url}
        except Exception:
            pass  # no proxies available, continue without

    if jsessionid:
        s.cookies.set('JSESSIONID', jsessionid, domain='tickets.museivaticani.va')
    if ticketmv:
        s.cookies.set('ticketmv', ticketmv, domain='tickets.museivaticani.va')
    if serverid:
        s.cookies.set('SERVERID', serverid, domain='tickets.museivaticani.va')

    return s


def test_epay_ssl():
    """Quick test — returns True if epay.catholica.va TLS handshake succeeds."""
    try:
        s = requests.Session()
        s.mount('https://epay.catholica.va', EpaySSLAdapter())
        r = s.get('https://epay.catholica.va/pay/SIV001/upp/auth/start.page', timeout=8)
        # 405 = POST-only endpoint, but TLS succeeded
        return r.status_code in (200, 302, 405, 400)
    except Exception:
        return False
