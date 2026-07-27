"""
Customer Care Bot — Entry Point
================================
Bridge module: docker-compose expects customer_care.bot.run,
so this delegates to the actual entry point in __main__.py.
"""
from customer_care.bot.__main__ import main

if __name__ == "__main__":
    main()
