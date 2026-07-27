import os, sys, django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.db import connection

with connection.cursor() as c:
    # Remove bad migration record
    c.execute("DELETE FROM django_migrations WHERE app='monitors' AND name='0021_add_bulk_hold_config'")
    print("Removed bad migration record")

    # Drop the wrongly-named bulk_hold_configs table (it was created manually)
    c.execute("DROP TABLE IF EXISTS bulk_hold_configs CASCADE")
    print("Dropped bulk_hold_configs")

    # Ensure dynamic_injection_configs has correct schema for the old model
    # (it still exists in models.py so Django needs it)
    c.execute("DROP TABLE IF EXISTS dynamic_injection_configs CASCADE")
    c.execute("""
        CREATE TABLE dynamic_injection_configs (
            id SERIAL PRIMARY KEY,
            task_id INTEGER NOT NULL DEFAULT 0,
            buyer_profile_id INTEGER NOT NULL DEFAULT 0,
            agency_id INTEGER NOT NULL DEFAULT 0,
            participant_overrides TEXT NOT NULL DEFAULT '[]',
            card_overrides TEXT NOT NULL DEFAULT '{}',
            action VARCHAR(10) NOT NULL DEFAULT 'epay',
            expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            is_used BOOLEAN NOT NULL DEFAULT FALSE,
            used_at TIMESTAMPTZ NULL,
            result_epay_url TEXT NULL,
            result_snipe_status VARCHAR(50) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    print("Recreated dynamic_injection_configs with correct schema")

print("Done")
