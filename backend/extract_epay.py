"""Get the /epay/process/ response body - this gives us the SIV transaction ID"""
import re, json

with open('/app/epay.catholica.va.txt', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Find /epay/process/ entry and get its response
urlms_pos = content.find('/epay/process/')
if urlms_pos != -1:
    # Get the response section
    resp_start = content.find('"response"', urlms_pos)
    resp_end = content.find('"_connectionId"', resp_start)
    resp = content[resp_start:resp_end]
    print("=== /epay/process/ RESPONSE ===")
    print(resp[:3000])
    
    # Find the text body
    text_pos = resp.find('"text"')
    if text_pos != -1:
        print("\n=== RESPONSE BODY ===")
        print(resp[text_pos:text_pos+2000])

# Also find the request to /epay/process/
req_start = content.rfind('"request"', 0, urlms_pos)
print("\n\n=== /epay/process/ REQUEST ===")
print(content[req_start:req_start+1500])

# Find the securefields/init request body
sf_pos = content.find('/api/securefields/init')
req_start2 = content.rfind('"request"', 0, sf_pos)
print("\n\n=== securefields/init REQUEST ===")
print(content[req_start2:req_start2+2000])
