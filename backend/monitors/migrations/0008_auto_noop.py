from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('monitors', '0007_fix_owner_id_schema'),
    ]

    operations = [
        # No-op migration to fill the gap between 0007 and 0009.
        # Migration 0008 was never created in the original project;
        # 0009 depends directly on 0007, so this is a safe no-op.
    ]
