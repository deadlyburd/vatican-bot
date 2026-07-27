"""
Command-line interface for the Vatican Bot agent system.

Usage:
    python -m agent.cli pipeline       # Run the booking pipeline
    python -m agent.cli customer-bot   # Run the customer Telegram bot
    python -m agent.cli check          # Check slots for today + 60 days
    python -m agent.cli check --date 01/08/2026  # Check specific date
    python -m agent.cli book --date 01/08/2026 --visitors 2  # One-off booking
    python -m agent.cli status         # Show system status
"""

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta

from agent.config import config, get_config

logger = logging.getLogger(__name__)


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Vatican Bot Agent — ticket monitoring and booking",
        prog="vatican-bot",
    )
    sub = parser.add_subparsers(dest="command", help="Command to run")

    # pipeline
    sub.add_parser("pipeline", help="Run the booking pipeline continuously")

    # customer-bot
    sub.add_parser("customer-bot", help="Run the customer-facing Telegram bot")

    # local-worker
    worker_parser = sub.add_parser("local-worker", help="Run the local booking worker (desktop)")
    worker_parser.add_argument("--cdp-port", type=int, default=9222, help="Chrome DevTools port")
    worker_parser.add_argument("--interval", type=int, default=30, help="Poll interval in seconds")

    # check
    check_parser = sub.add_parser("check", help="Check Vatican API for available slots")
    check_parser.add_argument("--date", help="Date in DD/MM/YYYY (default: today)")
    check_parser.add_argument("--visitors", type=int, default=2, help="Number of visitors")
    check_parser.add_argument("--scan", type=int, default=1,
                              help="Scan N days forward (default: 1 = just the given date)")

    # book
    book_parser = sub.add_parser("book", help="Book a single ticket")
    book_parser.add_argument("--date", required=True, help="Date in DD/MM/YYYY")
    book_parser.add_argument("--visitors", type=int, default=2, help="Number of visitors")
    book_parser.add_argument("--email", default="", help="Buyer email")
    book_parser.add_argument("--first-name", default="", help="Buyer first name")
    book_parser.add_argument("--last-name", default="", help="Buyer last name")
    book_parser.add_argument("--phone", default="", help="Buyer phone number")
    book_parser.add_argument("--headless", action="store_true", help="Run browser headless")

    # status
    sub.add_parser("status", help="Show system configuration and status")

    # sheets
    sub.add_parser("sheets", help="List pending bookings from Google Sheets")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Run the command
    if args.command == "pipeline":
        cmd_pipeline()
    elif args.command == "customer-bot":
        cmd_customer_bot()
    elif args.command == "local-worker":
        cmd_local_worker(args)
    elif args.command == "check":
        cmd_check(args)
    elif args.command == "book":
        asyncio.run(cmd_book(args))
    elif args.command == "status":
        cmd_status()
    elif args.command == "sheets":
        cmd_sheets()


# ── Commands ────────────────────────────────────────────────────────────────

def cmd_pipeline():
    """Run the booking pipeline."""
    from agent.pipeline import Pipeline
    pipeline = Pipeline()
    pipeline.run()


def cmd_customer_bot():
    """Run the customer Telegram bot."""
    from agent.customer_bot import CustomerBot
    bot = CustomerBot()
    bot.run_polling()


def cmd_local_worker(args):
    """Run the local booking worker (desktop)."""
    from agent.local_worker import LocalWorker
    worker = LocalWorker(cdp_port=args.cdp_port, poll_interval=args.interval)
    worker.run()


def cmd_check(args):
    """Check Vatican API for available slots."""
    from agent.vatican_api import SlotFinder

    finder = SlotFinder()
    target = args.date or date.today().strftime("%d/%m/%Y")

    print(f"🔍 Checking Vatican slots...")
    print(f"   Date: {target}, Visitors: {args.visitors}")
    print(f"   Proxy: {'enabled' if config.oxylabs_username else 'DISABLED'}")

    if args.scan > 1:
        print(f"   Scanning {args.scan} days forward...\n")
        slot = finder.find_next_available(target, args.scan, args.visitors)
        if slot:
            print(f"\n✅ First available: {slot}")
        else:
            print(f"\n❌ No slots found in next {args.scan} days")
    else:
        slots = finder.find_slots(target, args.visitors, use_cache=False)
        if slots:
            print(f"\n✅ Found {len(slots)} available slot(s):")
            for s in slots:
                print(f"   {s.time} — €{s.price} ({s.residual} tickets left)")
        else:
            print(f"\n❌ No slots available for {target}")


async def cmd_book(args):
    """Book a single ticket."""
    from agent.vatican_api import SlotFinder
    from agent.booker import BuyerInfo, Participant, VaticanBooker

    # Default buyer info from config
    first_name = args.first_name or config.buyer_default_name or "Guest"
    last_name = args.last_name or config.buyer_default_surname or "Guest"
    email = args.email or config.buyer_default_email or "booking@example.com"
    phone = args.phone or config.buyer_default_phone or "0000000000"

    # Check slots
    finder = SlotFinder()
    slots = finder.find_slots(args.date, args.visitors, use_cache=False)

    if not slots:
        print(f"❌ No slots available for {args.date}")
        return

    slot = slots[0]
    print(f"✅ Slot found: {slot.date} {slot.time}")
    print(f"   Booking for {first_name} {last_name} ({args.visitors}v)")
    print(f"   Email: {email}")

    # Confirm
    if not args.headless:
        confirm = input("\nProceed with booking? [y/N] ")
        if confirm.lower() != "y":
            print("Cancelled.")
            return

    buyer = BuyerInfo(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
    )

    participants = []
    for i in range(args.visitors):
        participants.append(Participant(
            first_name=first_name if i == 0 else f"Guest{i + 1}",
            last_name=last_name,
        ))

    booker = VaticanBooker(headless=args.headless)
    result = await booker.book(slot, buyer, participants)

    if result["success"]:
        print(f"\n✅ BOOKED!")
        print(f"   Payment URL: {result['epay_url']}")
    else:
        print(f"\n❌ Failed: {result.get('error', 'Unknown error')}")


def cmd_status():
    """Show system configuration and status."""
    cfg = get_config()
    print(cfg.summary())
    warnings = cfg.validate()
    if warnings:
        print(f"\n⚠️  Warnings:")
        for w in warnings:
            print(f"   - {w}")
    else:
        print(f"\n✅ All configuration looks good.")


def cmd_sheets():
    """List pending bookings from Google Sheets."""
    from agent.sheets import get_sheets

    sheets = get_sheets()
    print("🔍 Reading Google Sheets...")
    print(f"   Sheet ID: {config.google_sheet_id[:20]}...")
    print()

    pending = sheets.get_pending_bookings()
    if not pending:
        print("✅ No pending bookings — all caught up!")
        return

    print(f"📋 {len(pending)} booking(s) need tickets:\n")
    for b in pending:
        print(f"   {b.date} {b.time} | {b.first_name} {b.last_name} | "
              f"{b.pax}v | {b.product[:30]} | ID: {b.booking_id}")


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    main()
