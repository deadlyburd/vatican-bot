#!/usr/bin/env python3
"""Check Chrome status on the server."""
import subprocess, json

# Check all 3 bots
for bot_id in [1, 2, 3]:
    port = 9221 + bot_id
    try:
        result = subprocess.run(
            ["curl", "-s", f"http://localhost:{port}/json"],
            capture_output=True, text=True, timeout=5
        )
        tabs = json.loads(result.stdout)
        print(f"Bot #{bot_id} (port {port}): {len(tabs)} tab(s)")
        for t in tabs[:2]:
            ttl = t.get('title', '')[:80]
            url = t.get('url', '')[:80]
            print(f"  Title: {ttl}")
            print(f"  URL: {url}")
    except Exception as e:
        print(f"Bot #{bot_id}: Error - {e}")
