import os
import sys
from datetime import datetime, timedelta, timezone
import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

EAT = timezone(timedelta(hours=3))

# ==========================================
# 1. CONNECT TO FIREBASE
# ==========================================
CREDENTIALS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'firebase_key.json'))
DATABASE_URL = os.getenv("FIREBASE_DB_URL", "https://mmust-dating-site-default-rtdb.firebaseio.com/")

def initialize_firebase():
    if not firebase_admin._apps:
        try:
            if not os.path.exists(CREDENTIALS_PATH):
                print(f"ERROR: Cannot find firebase_key.json at {CREDENTIALS_PATH}")
                sys.exit(1)
            cred = credentials.Certificate(CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})
            print("Connected to Firebase database.")
        except Exception as e:
            print(f"Connection failed: {e}")
            sys.exit(1)

# ==========================================
# 2. CLEAR FUNCTIONS
# ==========================================

def clear_pending_payments():
    """Deletes all payment transaction logs (pending_payments node)."""
    try:
        ref = db.reference("pending_payments")
        data = ref.get() or {}
        count = len(data)
        ref.delete()
        print(f"  [OK] Cleared pending_payments  - {count} records removed.")
    except Exception as e:
        print(f"  [FAIL] pending_payments: {e}")

def clear_ledger():
    """Deletes all B2B ledger entries."""
    try:
        ref = db.reference("ledger")
        data = ref.get() or {}
        count = len(data)
        ref.delete()
        print(f"  [OK] Cleared ledger            - {count} records removed.")
    except Exception as e:
        print(f"  [FAIL] ledger: {e}")

def clear_manual_revenue_overrides():
    """Resets any manual revenue overrides set from the admin dashboard."""
    try:
        ref = db.reference("system_settings/manual_revenue_overrides")
        ref.delete()
        print(f"  [OK] Cleared manual_revenue_overrides.")
    except Exception as e:
        print(f"  [FAIL] manual_revenue_overrides: {e}")

def reset_restaurant_subscriptions():
    """
    Resets subscription fields on all restaurants to inactive.
    Does NOT delete the restaurants themselves.
    After this, use unlock_business.py to re-activate merchants.
    """
    try:
        restaurants_ref = db.reference("restaurants")
        all_restaurants = restaurants_ref.get() or {}
        count = 0
        for r_id in all_restaurants:
            restaurants_ref.child(r_id).update({
                "subscription_active": False,
                "subscription_start": None,
                "subscription_expiry": None,
                "last_payment_receipt": None,
            })
            count += 1
        print(f"  [OK] Reset subscription data on {count} restaurant(s).")
    except Exception as e:
        print(f"  [FAIL] restaurant subscriptions: {e}")

# ==========================================
# 3. MAIN ENTRY POINT
# ==========================================
if __name__ == "__main__":
    print()
    print("=" * 55)
    print("   ADMIN HISTORY RESET TOOL")
    print("   Clears payment + revenue history from Firebase")
    print("=" * 55)

    initialize_firebase()

    print()
    print("The following data will be PERMANENTLY deleted:")
    print("  - pending_payments           (all M-Pesa logs)")
    print("  - ledger                     (all B2B entries)")
    print("  - manual_revenue_overrides   (admin corrections)")
    print()

    confirm = input("Type YES to confirm and proceed: ").strip()
    if confirm != "YES":
        print()
        print("Aborted. No changes were made.")
        sys.exit(0)

    print()
    print("Starting cleanup...")
    print()
    clear_pending_payments()
    clear_ledger()
    clear_manual_revenue_overrides()

    print()
    also_reset = input("Also reset restaurant subscription data? (y/n): ").strip().lower()
    if also_reset == "y":
        reset_restaurant_subscriptions()
        print()
        print("Done! Use unlock_business.py to re-activate merchants.")
    else:
        print("Skipped restaurant subscription reset.")

    print()
    print("=" * 55)
    print("   CLEANUP COMPLETE - Dashboard starts fresh now.")
    print("=" * 55)
    print()
