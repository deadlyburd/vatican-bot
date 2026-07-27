from django.core.management.base import BaseCommand
from monitors.models import Agency, MonitorTask

class Command(BaseCommand):
    help = 'Seeds the database with initial enterprise data'

    def handle(self, *args, **kwargs):
        # Create Sample Agency
        agency, created = Agency.objects.get_or_create(
            name="Alpha Travel Agency",
            defaults={
                "api_key": "alpha-123456789",
                "telegram_chat_id": ""
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created Agency: {agency.name}'))
        else:
            self.stdout.write(self.style.WARNING(f'Agency {agency.name} already exists'))

        # Create Sample Vatican Task
        task1, created = MonitorTask.objects.get_or_create(
            agency=agency,
            site='vatican',
            area_name='Musei Vaticani - Biglietti',
            defaults={
                "dates": ["2026-06-15", "2026-06-16"],
                "preferred_times": ["09:00", "10:30", "14:00"],
                "visitors": 2,
                "ticket_type": 0,
                "language": "Italiano"
            }
        )

        # Create Sample Colosseum Task
        task2, created = MonitorTask.objects.get_or_create(
            agency=agency,
            site='colosseum',
            area_name='Parco Colosseo 24h',
            defaults={
                "dates": ["2026-07-20"],
                "preferred_times": ["11:00", "15:00"],
                "visitors": 4
            }
        )

        self.stdout.write(self.style.SUCCESS('Successfully seeded V2 Enterprise data!'))
