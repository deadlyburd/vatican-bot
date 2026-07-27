import requests

r = requests.get('http://localhost:8000/api/v1/holds/152/checkout/', timeout=20)
print(f'Status: {r.status_code}')
print(f'Content-Type: {r.headers.get("content-type")}')
print(f'Length: {len(r.text)} chars')
print(f'Body preview:\n{r.text[:500]}')
