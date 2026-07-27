"""Create bulk_hold_configs table directly"""
import os, sys, django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.db import connection

with connection.cursor() as c:
    # Check if table exists
    c.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name='bulk_hold_configs')")
    exists = c.fetchone()[0]
    print(f"bulk_hold_configs exists: {exists}")

    if not exists:
        c.execute("""
            CREATE TABLE bulk_hold_configs (
                id SERIAL PRIMARY KEY,
                agency_id INTEGER NOT NULL,
                date_from DATE NOT NULL,
                date_to DATE NOT NULL,
                time_from VARCHAR(5) NOT NULL DEFAULT '08:00',
                time_to VARCHAR(5) NOT NULL DEFAULT '17:00',
                visitors INTEGER NOT NULL DEFAULT 2,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                total_locked INTEGER NOT NULL DEFAULT 0,
                last_scan_at TIMESTAMP WITH TIME ZONE NULL
            )
        """)
        print("✅ Created bulk_hold_configs table")
    else:
        print("Table already exists")

    # Also check dynamic_injection_configs
    c.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name='dynamic_injection_configs')")
    dic_exists = c.fetchone()[0]
    print(f"dynamic_injection_configs exists: {dic_exists}")
