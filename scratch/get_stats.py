import sys
import os
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from database import db, initialize_firebase

initialize_firebase()
profiles_ref = db.reference('profiles')
all_profiles = profiles_ref.get() or {}

total_users = len(all_profiles)

active_last_2_days = 0
bestie_share_referrers = 0
bestie_share_invitees = 0

now_utc = datetime.now(timezone.utc)
two_days_ago = now_utc - timedelta(days=2)

for uid, data in all_profiles.items():
    if isinstance(data, dict):
        # 1. Check last seen
        last_seen = data.get('last_seen', '')
        if last_seen:
            try:
                # Handle isoformat
                ls_dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                # convert ls_dt to utc if it has tzinfo
                if ls_dt.tzinfo:
                    ls_dt_utc = ls_dt.astimezone(timezone.utc)
                else:
                    ls_dt_utc = ls_dt.replace(tzinfo=timezone.utc)
                
                if ls_dt_utc >= two_days_ago:
                    active_last_2_days += 1
            except Exception as e:
                pass
                
        # 2. Check VIP Referrals (Referrers)
        # Auth.py increments 'referrals_count' and 'free_weeks_earned'
        if data.get('free_weeks_earned', 0) > 0 or data.get('referrals_count', 0) > 0:
            bestie_share_referrers += 1
            
        # 3. Check VIP Referrals (Invitees)
        receipt = data.get('last_payment_receipt', '')
        if 'SYSTEM_PROMO' in receipt:
            bestie_share_invitees += 1

print(f"Total Users: {total_users}")
print(f"Active in last 2 days: {active_last_2_days}")
print(f"Users who invited friends (Bestie Share Referrers): {bestie_share_referrers}")
print(f"Users who were invited (Bestie Share Invitees): {bestie_share_invitees}")
