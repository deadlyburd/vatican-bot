import requests
import time
import sys
import os

# Set up Django environment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

from monitors.models import HeldSlot
from monitors.hold_manager import keepalive_slot, hold_slot
from monitors.models import MonitorTask

def verify_keepalive(hold_id):
    """
    Verification script for Vatican slot hold stability.
    Goal: Maintain a hold for 70 minutes.
    """
    try:
        hold = HeldSlot.objects.get(id=hold_id)
    except HeldSlot.DoesNotExist:
        print(f"❌ Hold #{hold_id} not found.")
        return

    print(f"🚀 Starting verification for Hold #{hold.id}...")
    print(f"📅 Date: {hold.date} {hold.slot_time}")
    print(f"🕒 Started at: {hold.hold_started_at}")
    
    start_time = time.time()
    next_ping = start_time + 300 # 5 minutes
    
    try:
        # We'll run for 70 minutes (4200 seconds)
        # To make this feasible for a test run, we can just simulate the check 
        # or do a shorter run that monitors the RecapId change.
        while (time.time() - start_time) < 4200:
            current_elapsed = (time.time() - start_time) / 60
            print(f"⏱️ Elapsed: {current_elapsed:.1f} min... ", end="", flush=True)
            
            if time.time() >= next_ping:
                print("\n💓 Sending keepalive ping...")
                success = keepalive_slot(hold)
                if success:
                    print(f"✅ Keepalive successful. New RecapId: {hold.recap_id}")
                    next_ping = time.time() + 300
                else:
                    print("❌ Keepalive failed!")
                    break
            else:
                print("OK", end="\r")
            
            time.sleep(10)
            
        total_min = (time.time() - start_time) / 60
        print(f"\n🏁 Verification complete! Total hold time: {total_min:.1f} minutes.")
        
    except KeyboardInterrupt:
        print("\n⏹️ Stopped by user.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, help="ID of the HeldSlot to verify")
    args = parser.parse_args()
    
    if args.id:
        verify_keepalive(args.id)
    else:
        print("Usage: python test_keepalive_proof.py --id <HOLD_ID>")
