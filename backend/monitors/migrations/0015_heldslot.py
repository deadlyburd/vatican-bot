from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('monitors', '0014_add_super_admin_field'),
    ]

    operations = [
        migrations.CreateModel(
            name='HeldSlot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='held_slots', to='monitors.monitortask')),
                ('date', models.CharField(max_length=20, help_text='DD/MM/YYYY')),
                ('slot_id', models.CharField(max_length=50, help_text='e.g. 2026*8776')),
                ('slot_time', models.CharField(max_length=10, help_text='e.g. 12:00')),
                ('ticket_id', models.CharField(max_length=50)),
                ('ticket_name', models.CharField(max_length=300)),
                ('visitors', models.PositiveIntegerField(default=2)),
                ('total_price', models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)),
                ('jsessionid', models.CharField(max_length=255, help_text='Vatican session cookie')),
                ('ticketmv', models.CharField(max_length=50, blank=True, null=True)),
                ('status', models.CharField(max_length=20, default='held',
                    choices=[('held','Held'),('paying','Paying'),('paid','Paid'),('released','Released'),('expired','Expired')])),
                ('hold_started_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('last_keepalive_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('released_at', models.DateTimeField(null=True, blank=True)),
                ('payment_url', models.TextField(null=True, blank=True)),
                ('notes', models.TextField(blank=True, null=True)),
            ],
            options={
                'db_table': 'held_slots',
                'ordering': ['-hold_started_at'],
            },
        ),
    ]
