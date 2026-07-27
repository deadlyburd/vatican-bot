#!/usr/bin/env python3
"""
God-Tier Vatican Monitor CLI
============================
Quick launcher for the ultra-fast headless monitor.

Usage:
    python run_god_tier.py --dates 10/02/2026 11/02/2026 --type standard
    python run_god_tier.py --dates 10/02/2026 --type guided --interval 60
    python run_god_tier.py --init-only  # Just refresh session and exit
"""

import argparse
import asyncio
import sys
from datetime import datetime

from god_tier_monitor import GodTierVaticanMonitor, SESSION_FILE


def parse_args():
    parser = argparse.ArgumentParser(
        description="God-Tier Vatican Ticket Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Monitor standard tickets for specific dates
  python run_god_tier.py --dates 10/02/2026 11/02/2026 --type standard
  
  # Monitor guided tours with 60-second interval
  python run_god_tier.py --dates 10/02/2026 --type guided --interval 60
  
  # Just initialize session (harvest IDs) and exit
  python run_god_tier.py --init-only --dates 10/02/2026
  
  # Run for only 10 cycles
  python run_god_tier.py --dates 10/02/2026 --cycles 10
        """
    )
    
    parser.add_argument(
        "--dates",
        nargs="+",
        required=True,
        help="Dates to monitor (format: DD/MM/YYYY)"
    )
    
    parser.add_argument(
        "--type",
        choices=["standard", "guided"],
        default="standard",
        help="Ticket type (default: standard)"
    )
    
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Check interval in seconds (default: 30)"
    )
    
    parser.add_argument(
        "--cycles",
        type=int,
        default=None,
        help="Max number of cycles (default: infinite)"
    )
    
    parser.add_argument(
        "--init-only",
        action="store_true",
        help="Only initialize session (get cookies + IDs) and exit"
    )
    
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run single test check and exit"
    )
    
    return parser.parse_args()


async def main():
    args = parse_args()
    
    # Convert ticket type
    ticket_type = 0 if args.type == "standard" else 1
    
    print("=" * 70)
    print("🐉 VATICAN GOD-TIER MONITOR")
    print("=" * 70)
    print(f"📅 Dates: {', '.join(args.dates)}")
    print(f"🎫 Type: {args.type.title()}")
    print(f"⏱️  Interval: {args.interval}s")
    if args.cycles:
        print(f"🔁 Cycles: {args.cycles}")
    print("=" * 70)
    
    # Initialize monitor
    monitor = GodTierVaticanMonitor()
    
    # Test mode - single check
    if args.test:
        print("\n🧪 TEST MODE - Single check\n")
        for date in args.dates:
            print(f"Checking {date}...")
            results = await monitor.check_availability_headless(date, ticket_type)
            
            if results:
                print(f"✅ FOUND {len(results)} available tickets:")
                for r in results:
                    slots = ", ".join([s['time'] for s in r['slots'][:5]])
                    print(f"   🎫 {r['ticket_name']} ({r['language']})")
                    print(f"      Slots: {slots}")
            else:
                print(f"❌ No availability")
        return
    
    # Init-only mode
    if args.init_only:
        print("\n🔧 INIT MODE - Refreshing session...\n")
        success = await monitor.refresh_session_with_browser(
            ticket_type=ticket_type,
            target_date=args.dates[0]
        )
        if success:
            print("✅ Session initialized successfully!")
            print(f"💾 Session saved (last updated: {monitor.session_cache.get('last_updated', 'unknown')})")
        else:
            print("❌ Failed to initialize session")
            sys.exit(1)
        return
    
    # Full monitoring mode
    print("\n🚀 Starting monitor loop...\n")
    try:
        await monitor.monitor_dates(
            dates=args.dates,
            ticket_type=ticket_type,
            interval_seconds=args.interval,
            max_cycles=args.cycles
        )
    except KeyboardInterrupt:
        print("\n\n👋 Monitor stopped by user")


if __name__ == "__main__":
    asyncio.run(main())
