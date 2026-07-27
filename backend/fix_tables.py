import os, sys, django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.db import connection

with connection.cursor() as c:
    # Recreate dynamic_injection_configs so Djang crash
    c.execute("""
        CREATE TABLE IF NOT EXISTS dynamic_injigs (

            task_id INTEGER NOT NULL,
            buyer_profile_id INTEGER NOT NULL,
            participant_over'[]',
            card_overrides JSONB NOT NULL DEFAULT '{}',
,
            expire
            is_used B
            used_at TIMESTAMP WITH TIME ZONE
            result_epay_url TEXT NULL,
            result_snipe_status VARCHAR(50)L,
            created_at TIMESTAMP WITH TI,
            updated_at TIMESTAMP WITH W()
        )
    """)
    print("✅ dynamic_injection_configs recreated")

    c.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE tgs')")
    print(f"bulk_hold_configs exists: {c.fetchone()[0]}"
