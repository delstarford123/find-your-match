import os, sys, logging
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from database import initialize_firebase, db

logging.basicConfig(level=logging.ERROR) # suppress verbose logs

def get_skipped():
    initialize_firebase()
    profiles_ref = db.reference('profiles')
    profiles = profiles_ref.get() or {}
    
    expiry_dt = datetime(2026, 9, 18, 9, 0, 0, tzinfo=timezone.utc)
    
    skipped_users = []
    
    for uid, user in profiles.items():
        if isinstance(user, dict):
            current_expiry_str = user.get('subscription_expiry', '')
            has_better_sub = False
            
            if user.get('is_paid') and current_expiry_str:
                try:
                    curr_dt = datetime.fromisoformat(current_expiry_str.replace('Z', '+00:00'))
                    if curr_dt > expiry_dt:
                        has_better_sub = True
                except:
                    pass
            
            if has_better_sub:
                name = user.get('name') or user.get('username') or 'Unknown'
                email = user.get('email', 'No Email')
                phone = user.get('phone', 'No Phone')
                expiry = current_expiry_str
                skipped_users.append(f"- {name} | {email} | {phone} | Expiry: {expiry}")
                
    print(f"--- LIST OF {len(skipped_users)} USERS WHO ALREADY HAVE A PREMIUM SUBSCRIPTION PAST FRIDAY ---")
    for u in skipped_users:
        print(u)

if __name__ == "__main__":
    get_skipped()
