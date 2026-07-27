#!/usr/bin/env python3
import argparse
import asyncio
import json
import os
import sys

# Ensure module path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

def parse_args():
    p = argparse.ArgumentParser(description="One-off Vatican availability check (direct IP or proxy)")
    p.add_argument("--date", required=True, help="Date to check (DD/MM/YYYY or YYYY-MM-DD)")
    p.add_argument("--type", choices=["standard","guided"], default="standard", help="Ticket type")
    p.add_argument("--lang", default=None, help="Language for guided tours (e.g., ENG, ITA)")
    p.add_argument("--no-proxy", action="store_true", help="Force direct IP (disable proxies)")
    return p.parse_args()

async def main():
    args = parse_args()
    ticket_type = 0 if args.type == "standard" else 1
    languages = [args.lang] if (ticket_type == 1 and args.lang) else (["ITA"] if ticket_type == 0 else ["ENG"])
    
    try:
        from god_tier_monitor_v2 import GodTierVaticanMonitorV2
        monitor_cls = GodTierVaticanMonitorV2
        method_name = "check_availability"
    except Exception:
        from god_tier_monitor import GodTierVaticanMonitor
        monitor_cls = GodTierVaticanMonitor
        method_name = "check_availability_headless"
    
    proxies = [] if args.no_proxy else None
    monitor = monitor_cls(proxies=proxies)
    
    fn = getattr(monitor, method_name)
    results = await fn(date_str=args.date, ticket_type=ticket_type, languages=languages)
    
    print(json.dumps({
        "date": args.date,
        "type": args.type,
        "language": args.lang,
        "using_proxy": not args.no_proxy,
        "found": len(results),
        "results": results
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    asyncio.run(main())

