import re
with open('D:/bot/travelagenntbot/websocket.har', 'rb') as f:
    raw = f.read()
content = raw.decode('utf-8', errors='replace')
content_clean = re.sub(r'[\x00-\x1f]', ' ', content)

# Find reservation response section
idx = content_clean.find('recapId')
chunk = content_clean[idx:idx+6000]

resp_start = chunk.find('"response"')
if resp_start > 0:
    resp_chunk = chunk[resp_start:resp_start+3000]
    print(resp_chunk[:3000])
