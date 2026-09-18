import os
from datetime import datetime, timedelta, timezone
import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv

load_dotenv()
EAT = timezone(timedelta(hours=3))
CREDENTIALS_PATH = os.path.abspath('firebase_key.json')
DATABASE_URL = os.getenv('FIREBASE_DB_URL', 'https://mmust-dating-site-default-rtdb.firebaseio.com/')

if not firebase_admin._apps:
    cred = credentials.Certificate(CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})

now = datetime.now(EAT)
month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

all_profiles = db.reference('profiles').get() or {}
results = []

for uid, data in all_profiles.items():
    if not isinstance(data, dict):
        continue
    raw_date = (
        data.get('created_at') or data.get('registered_at') or
        data.get('joined_at') or data.get('signup_date') or data.get('date_joined')
    )
    if not raw_date:
        continue
    try:
        date_str = str(raw_date).replace('Z', '+00:00')
        reg_dt = datetime.fromisoformat(date_str)
        if reg_dt.tzinfo is None:
            reg_dt = reg_dt.replace(tzinfo=EAT)
        if reg_dt >= month_start:
            phone = (
                data.get('phone') or data.get('phone_number') or
                data.get('mpesa_phone') or data.get('contact') or 'N/A'
            )
            results.append({
                'name':  data.get('name', 'Unknown'),
                'email': data.get('email', 'N/A'),
                'phone': phone,
                'reg':   reg_dt,
            })
    except Exception:
        pass

results.sort(key=lambda x: x['reg'], reverse=True)

print()
print("  August 2026 — Registered Users — Phone & Email")
print("  " + "-" * 60)
for i, u in enumerate(results, 1):
    print(f"  {i}. {u['name']}")
    print(f"     Email : {u['email']}")
    print(f"     Phone : {u['phone']}")
    print(f"     Joined: {u['reg'].strftime('%Y-%m-%d %H:%M EAT')}")
    print()
