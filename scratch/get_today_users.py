import sys
import os
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from database import db, initialize_firebase

initialize_firebase()
all_profiles = db.reference('profiles').get() or {}

print("Users who created an account on 2026-09-18:")
count = 0
for uid, data in all_profiles.items():
    if isinstance(data, dict):
        created_at = data.get('created_at', '')
        if created_at.startswith('2026-09-18'):
            count += 1
            print(f"- Name: {data.get('name', 'N/A')}, Email: {data.get('email', 'N/A')}, Created At: {created_at}")

print(f"Total: {count}")
