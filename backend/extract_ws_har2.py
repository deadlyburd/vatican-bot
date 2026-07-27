import re, json

with open('D:/bot/travelagenntbot/websocket.har', 'rb') as f:
    raw = f.read()
content = raw.decode('utf-8', errors='replace')

# Find the reservation response
idx = content.find('"recapId":"2026/9389/61"')
chunk = content[idx:idx+5000]
chunk_clean = re.sub(r'[\x00-\x1f]', ' ', chunk)

# Extract the response text
resp_m = re.search(r'"response".*?"text":\s*"(\{[^"]*(?:\\"[^"]*)*\})"', chunk_clean)
if resp_m:
    text = resp_m.group(1).replace('\\"', '"')
    try:
        print("RESERVATION RESPONSE:")
        print(json.dumps(json.loads(text), indent=2))
    except:
        print(text[:1000])
else:
    # Print the chunk after "response"
    resp_idx = chunk_clean.find('"response"')
    if resp_idx > 0:
        print("RESPONSE SECTION:")
        print(chunk_clean[resp_idx:resp_idx+2000])

# Also extract the full request body cleanly
req_text_m = re.search(r'"text":\s*"(\{.*?recapId.*?\})"', chunk_clean)
if req_text_m:
    text = req_text_m.group(1).replace('\\"', '"')
    try:
        body = json.loads(text)
        print("\nFULL RESERVATION REQUEST BODY:")
        print(json.dumps(body, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Parse error: {e}")
        print(text[:2000])

# Find cookies in the reservation request
idx2 = content.find('/api/visit/reservation')
chunk2 = content[idx2:idx2+3000]
chunk2_clean = re.sub(r'[\x00-\x1f]', ' ', chunk2)
cookie_m = re.search(r'"cookies":\s*\[(.*?)\]', chunk2_clean)
if cookie_m:
    print(f"\nCOOKIES: {cookie_m.group(1)[:500]}")
else:
    print("\nCOOKIES: none in HAR (sent via browser session)")
