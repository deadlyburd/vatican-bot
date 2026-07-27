# Generated migration for VaticanTask model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitors', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='VaticanTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('booking_id', models.CharField(db_index=True, help_text='Confirmation code from Google Sheets', max_length=100, unique=True)),
                ('target_date', models.DateField(help_text='Activity date')),
                ('target_time', models.CharField(help_text='Preferred time (HH:MM)', max_length=10)),
                ('visitors', models.PositiveIntegerField(default=1)),
                ('ticket_type', models.IntegerField(choices=[(0, 'Standard Ticket'), (1, 'Guided Tour')], default=0)),
                ('language', models.CharField(blank=True, help_text='Language code for guided tours (ENG, ITA, etc)', max_length=10, null=True)),
                ('customer_name', models.CharField(max_length=255)),
                ('customer_email', models.EmailField(max_length=254)),
                ('customer_phone', models.CharField(blank=True, max_length=50, null=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('monitoring', 'Monitoring'), ('available', 'Available'), ('booked', 'Booked'), ('failed', 'Failed'), ('cancelled', 'Cancelled')], default='pending', max_length=20)),
                ('priority', models.IntegerField(default=1, help_text='Higher = more urgent')),
                ('last_checked', models.DateTimeField(blank=True, null=True)),
                ('available_slots', models.TextField(blank=True, help_text='Comma-separated available time slots', null=True)),
                ('booked_time', models.CharField(blank=True, help_text='Actually booked time (HH:MM)', max_length=10, null=True)),
                ('checkout_url', models.TextField(blank=True, help_text='Epay checkout URL', null=True)),
                ('reference_code', models.CharField(blank=True, help_text='Vatican reference/order number', max_length=100, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'vatican_tasks',
                'ordering': ['target_date', '-priority', 'created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='vaticantask',
            index=models.Index(fields=['booking_id'], name='vt_booking_id_idx'),
        ),
        migrations.AddIndex(
            model_name='vaticantask',
            index=models.Index(fields=['status'], name='vt_status_idx'),
        ),
        migrations.AddIndex(
            model_name='vaticantask',
            index=models.Index(fields=['target_date'], name='vt_target_date_idx'),
        ),
    ]
