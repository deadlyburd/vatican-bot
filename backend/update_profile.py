import os, sys, django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import BuyerProfile, Agency
from datetime import date

# Update all active agencies with the new profile
agencies = Agency.objects.filter(is_active=True).exclude(plan='system')
for agency in agencies:
    profile, created = BuyerProfile.objects.update_or_create(
        agency=agency,
        defaults={
            'first_name': 'Great',
            'last_name': 'Aby',
            'email': 'your-email@example.com',
            'phone': '3517869798',
            'city': 'Roma',
            'country': 'Italy',
            'birth_date': date(2000, 7, 25),
            'gender': 'M',
            'language': 'en',
        }
    )
    action = 'created' if created else 'updated'
    print(f"{action}: {agency.name} — {profile.first_name} {profile.last_name} | {profile.email}")

print("\nDone. Profile will be used for all Vatican bookings.")
