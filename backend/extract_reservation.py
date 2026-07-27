"""Extract reservation request details from websocket.txt"""
import json, re

with open('/app/websocket.txt', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Find ALL reservation POST entries
idx = 0
while True:
    pos = content.find('/api/visit/reservation', idx)
    if pos == -1:
        break
    # Check if this is a POST (not a mention in text)
    nearby = content[max(0,pos-500):pos+100]
    if '"POST"' in nearby or 'postData' in content[pos:pos+3000]:
        print(f"\n{'='*60}")
        print(f"RESERVATION ENTRY at pos {pos}")
        # Get the postData text
        pd_start = content.find('"postData"', pos)
        if pd_start != -1 and pd_start < pos + 5000:
            pd_end = content.find('"}\n', pd_start) + 3
            print("POST BODY:")
            print(content[pd_start:pd_start+2000])
        # Get response content
        resp_start = content.find('"response"', pos)
        if resp_start != -1 and resp_start < pos + 8000:
            print("\nRESPONSE:")
            print(content[resp_start:resp_start+2000])
    idx = pos + 1
