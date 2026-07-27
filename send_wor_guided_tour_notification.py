#!/usr/bin/env python
"""
Send test notification to WOR showing available guided tour slots
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django
django.setup()

import requests
from datetime import datetime

def get_guided_tour_slots():
    """Get available guided tour slots"""
    print("🔍 Scanning for available guided tour slots...")
    
    dates = ['29/04/2026', '30/04/2026', '01/05/2026', '02/05/2026', '05/05/2026']
    results = []
    
    for date_str in dates:
        try:
            url = 'https://tickets.museivaticani.va/api/search/resultPerTag'
            params = {
                'lang': 'it',
                'visitorNum': '1',
                'visitDate': date_str,
                'area': '1',
                'who': '',
                'page': '0',
                'tag': 'MV-Visite-Guidate'  # Guided tours
            }
            
            headers = {
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': 'https://tickets.museivaticani.va/'
            }
            
            r = requests.get(url, params=params, headers=headers, timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                visits = data.get('visits', [])
                
                for visit in visits:
                    if visit.get('availability') == 'AVAILABLE':
                        # Get time slots
                        jsessionid = r.cookies.get('JSESSIONID', '')
                        
                        url2 = 'https://tickets.museivaticani.va/api/visit/timeavail'
                        params2 = {
                            'lang': 'it',
                            'visitLang': 'ENG',  # Check English tours
                            'visitTypeId': str(visit.get('id')),
                            'visitorNum': '1',
                            'visitDate': date_str
                        }
                        
                        headers2 = headers.copy()
                        if jsessionid:
                            headers2['Cookie'] = f'JSESSIONID={jsessionid}'
                        
                        r2 = requests.get(url2, params=params2, headers=headers2, timeout=10)
                        
                        if r2.status_code == 200:
                            timetable = r2.json().get('timetable', [])
                            available_slots = [s for s in timetable if s.get('availability') == 'AVAILABLE']
                            
                            if available_slots:
                                results.append({
                                    'date': date_str,
                                    'name': visit.get('name', 'Unknown'),
                                    'slots': [s['time'] for s in available_slots[:5]],
                                    'total_slots': len(available_slots)
                                })
                                print(f"✅ {date_str}: {visit.get('name')} - {len(available_slots)} slots")
                                break  # One tour per date is enough
                
        except Exception as e:
            print(f"⚠️  {date_str}: Error - {str(e)[:80]}")
    
    return results

def send_notification(slots_data):
    """Send notification to WOR Telegram group"""
    from monitors.notification_utils import send_telegram_signal
    
    if not slots_data:
        print("❌ No guided tour slots found to notify about")
        return False
    
    # Format message
    message = "🎉 **VATICAN GUIDED TOURS AVAILABLE!**\n\n"
    message += "📍 **Visite Guidate (Guided Tours)**\n"
    message += "🌍 Language: English\n"
    message += "👥 Visitors: 1\n\n"
    
    for item in slots_data[:5]:  # Show first 5 dates
        date_obj = datetime.strptime(item['date'], '%d/%m/%Y')
        date_formatted = date_obj.strftime('%B %d, %Y')
        
        message += f"📅 **{date_formatted}**\n"
        message += f"🎫 {item['name']}\n"
        message += f"⏰ Available times: {', '.join(item['slots'][:3])}"
        if item['total_slots'] > 3:
            message += f" (+{item['total_slots'] - 3} more)"
        message += "\n\n"
    
    message += "🔗 Book now: https://tickets.museivaticani.va/\n\n"
    message += "ℹ️ This is a TEST notification showing guided tour availability.\n"
    message += "Standard entry tickets are currently SOLD OUT."
    
    # WOR Bot group chat ID
    wor_chat_id = ''
    
    print(f"\n📤 Sending notification to WOR Bot group ({wor_chat_id})...")
    print(f"\n{message}\n")
    
    result = send_telegram_signal(wor_chat_id, message)
    
    if result:
        print(f"✅ Notification sent successfully!")
        return True
    else:
        print(f"❌ Failed to send notification")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("WOR GUIDED TOUR NOTIFICATION TEST")
    print("=" * 60)
    print()
    
    # Get available slots
    slots = get_guided_tour_slots()
    
    print()
    print(f"📊 Found {len(slots)} dates with available guided tours")
    print()
    
    if slots:
        # Send notification
        success = send_notification(slots)
        
        if success:
            print()
            print("=" * 60)
            print("✅ TEST COMPLETE - Check WOR Bot Telegram group!")
            print("=" * 60)
        else:
            print()
            print("=" * 60)
            print("❌ TEST FAILED - Check logs for errors")
            print("=" * 60)
    else:
        print("❌ No guided tour slots available for notification")
