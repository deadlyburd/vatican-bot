import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django
django.setup()

from monitors.models import Agency

CHAT_ID = os.environ.get("AGENCY_CHAT_ID", "")

def main():
    ag = Agency.objects.get(id=1)
    ag.telegram_chat_id = CHAT_ID
    ag.save(update_fields=['telegram_chat_id'])
    print(f"✅ Updated agency {ag.id} chat_id to {ag.telegram_chat_id}")

if __name__ == "__main__":
    main()

