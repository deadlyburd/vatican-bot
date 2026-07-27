cd backend && python manage.py shell << 'EOF'
from django.db import connection
from django.core.cache import cache

with connection.cursor() as c:
    # Get actual table names from Django
    c.execute("""
        SELECT tablename FROM pg_tables 
        WHERE schemaname='public' AND tablename LIKE 'monitors_%'
        ORDER BY tablename
    """)
    tables = [row[0] for row in c.fetchall()]
    print("Tables found:", tables)
    
    # Truncate in safe order
    for t in ['monitors_checkresult', 'held_slots', 'monitors_monitortask']:
        try:
            c.execute(f"TRUNCATE {t} CASCADE")
            print(f"Truncated {t}")
        except Exception as e:
            print(f"Skip {t}: {e}")

cache.clear()
print("Redis cache cleared")
print("Done.")
EOF
