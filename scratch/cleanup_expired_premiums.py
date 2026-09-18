import sys
import os
from datetime import datetime, timezone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from database import db, initialize_firebase

initialize_firebase()
profiles_ref = db.reference('profiles')
all_profiles = profiles_ref.get() or {}

print("Cleaning up expired premiums...")
count = 0

for uid, data in all_profiles.items():
    if isinstance(data, dict):
        is_paid = data.get('is_paid', False)
        expiry_str = data.get('subscription_expiry')
        
        has_expired = False
        if expiry_str:
            try:
                expiry_dt = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
                if datetime.now(timezone.utc) > expiry_dt:
                    has_expired = True
            except Exception as e:
                pass
                
        if is_paid and has_expired:
            profiles_ref.child(uid).update({'is_paid': False})
            count += 1

print(f"Cleaned up {count} expired premium accounts.")
