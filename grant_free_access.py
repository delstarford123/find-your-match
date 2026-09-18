import os, sys, logging, time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from database import initialize_firebase, db

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger("free_access")

def run():
    logger.info("=" * 60)
    logger.info("  GRANTING 2-DAY FREE PREMIUM ACCESS")
    logger.info("=" * 60)

    initialize_firebase()
    profiles_ref = db.reference('profiles')
    profiles = profiles_ref.get() or {}
    
    # Friday, September 18th, 2026 at 12:00 PM EAT (East Africa Time)
    # EAT is UTC+3. So 12:00 PM EAT = 09:00 AM UTC
    expiry_dt = datetime(2026, 9, 18, 9, 0, 0, tzinfo=timezone.utc)
    expiry_str = expiry_dt.isoformat()
    
    logger.info(f"Calculated Expiry Target: {expiry_str}")
    
    count = 0
    skipped = 0

    for uid, user in profiles.items():
        if isinstance(user, dict):
            current_expiry_str = user.get('subscription_expiry', '')
            has_better_sub = False
            
            # Smart check: If a user actually paid and their subscription lasts PAST this Friday,
            # we do not want to accidentally downgrade them or shorten their expiry!
            if user.get('is_paid') and current_expiry_str:
                try:
                    curr_dt = datetime.fromisoformat(current_expiry_str.replace('Z', '+00:00'))
                    if curr_dt > expiry_dt:
                        has_better_sub = True
                except:
                    pass
            
            if not has_better_sub:
                profiles_ref.child(uid).update({
                    'is_paid': True,
                    'subscription_expiry': expiry_str,
                    'subscription_package': 'gold' # Unlock standard premium features
                })
                count += 1
            else:
                skipped += 1
                
    logger.info("-" * 60)
    logger.info(f"✅ Granted 2-day free access to {count} users.")
    logger.info(f"⏭️ Skipped {skipped} users (they already had a longer paid subscription).")
    logger.info("=" * 60)

if __name__ == "__main__":
    run()
