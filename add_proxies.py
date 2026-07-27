#!/usr/bin/env python3
"""
Add proxies to the database for Vatican monitoring
Run this inside the Docker container:
docker exec -it travelagenntbot-backend-1 sh -c "cd backend && python ../add_proxies.py"
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import Proxy

# Your proxy list - ADD YOUR PROXIES HERE
PROXIES = [
    # Format: "ip:port:username:password"
    # Example: "142.111.48.253:7030:user123:pass456"
    
    # Add your proxies below (one per line):
    # "proxy1.example.com:8080:user1:pass1",
    # "proxy2.example.com:8080:user2:pass2",
    # "proxy3.example.com:8080:user3:pass3",
]

def add_proxies():
    """Add proxies to database"""
    added = 0
    skipped = 0
    
    for proxy_str in PROXIES:
        if not proxy_str or proxy_str.startswith('#'):
            continue
            
        parts = proxy_str.split(':')
        if len(parts) == 4:
            ip, port, username, password = parts
            ip_port = f"{ip}:{port}"
        elif len(parts) == 2:
            ip, port = parts
            ip_port = f"{ip}:{port}"
            username = ""
            password = ""
        else:
            print(f"⚠️ Invalid format: {proxy_str}")
            continue
        
        # Check if proxy already exists
        if Proxy.objects.filter(ip_port=ip_port).exists():
            print(f"⏭️ Skipped (exists): {ip_port}")
            skipped += 1
            continue
        
        # Add proxy
        Proxy.objects.create(
            ip_port=ip_port,
            username=username,
            password=password,
            is_active=True
        )
        print(f"✅ Added: {ip_port}")
        added += 1
    
    print(f"\n📊 Summary:")
    print(f"   Added: {added}")
    print(f"   Skipped: {skipped}")
    print(f"   Total active proxies: {Proxy.objects.filter(is_active=True).count()}")

if __name__ == '__main__':
    print("🔧 Adding proxies to database...\n")
    add_proxies()
