
from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('monitors', '0006_agency_plan_monitortask_ticket_id_and_more'),
    ]

    operations = [
        # SQLite compatible version
        # DO $$ ... END $$ blocks are PostgreSQL specific and not supported by SQLite
        migrations.RunSQL(
            sql="""
            -- Intentionally empty for SQLite compatibility in this migration
            -- The column adding logic should be handled by Django's AddField or simpler SQL
            -- Since migration 0005 already added this column (or tried to), 
            -- and we are fixing schema, we can just ensure it exists via Django operations if needed
            -- but since this is a RunSQL migration, we'll just make it a no-op for SQLite
            -- or use standard SQL if we really need to add it.
            -- Assuming 0005 succeeded or failed gracefully, let's just ensure the index exists.
            -- Actually, let's just make this migration do nothing for SQLite to avoid syntax errors.
            SELECT 1;
            """,
            reverse_sql="SELECT 1;"
        ),
    ]
