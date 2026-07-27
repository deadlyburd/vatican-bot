from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitors', '0017_buyerprofile_participants_json'),
    ]

    operations = [
        migrations.AddField(
            model_name='heldslot',
            name='recap_id',
            field=models.CharField(blank=True, help_text='e.g. 2026/8367/119 — needed for reservation', max_length=50, null=True),
        ),
    ]
