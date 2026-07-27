from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitors', '0016_buyerprofile'),
    ]

    operations = [
        migrations.AddField(
            model_name='buyerprofile',
            name='participants_json',
            field=models.TextField(blank=True, help_text='JSON list of participant names', null=True),
        ),
    ]
