#!/usr/bin/env python3
"""Check Activity_Lines worksheet for booking details"""

import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SERVICE_ACCOUNT_FILE = '/app/google_credentials.json'
SHEET_ID = '1YkDZgFZs-DiMJ9ECIECJZ3aNmpyWB66qzc2CeteI1Vg'

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID)

# Get Activity_Lines worksheet
worksheet = sheet.worksheet('Activity_Lines')
print(f"📋 Worksheet: {worksheet.title}")
print(f"   Rows: {worksheet.row_count}, Cols: {worksheet.col_count}")

# Get headers
headers = worksheet.row_values(1)
print(f"\n📋 Headers ({len(headers)} columns):")
for i, h in enumerate(headers, 1):
    print(f"   {i:2d}. {h}")

# Get sample data
print(f"\n📊 Sample Activity Lines (first 5):")
all_rows = worksheet.get_all_values()[1:6]

for idx, row in enumerate(all_rows, 1):
    activity = dict(zip(headers, row))
    print(f"\n   Activity #{idx}:")
    for key, value in activity.items():
        if value:  # Only show non-empty fields
            print(f"      {key}: {value}")
