import re, json, sys

with open('D:/bot/travelagenntbot/websocket.har', 'rb') as f:
    raw = f.read()
content = raw.decode('utf-8', errors='replace')

# Find the reservation payload around recapId
idx = content.find('"recapId":"2026/9389/61"')
if idx < 0:
    idx = content.find('recapId')
print(f"recapId found at position: {idx}")

# Extract surrounding context
chunk = content[max(0, idx-3000):idx+3000]
print("\n=== RAW CHUNK AROUND recapId ===")
# Clean control chars for display
chunk_clean = re.sub(r'[\x00-\x1f]', ' ', chunk)
print(chunk_clean[:5000])
