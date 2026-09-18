import sys
from app.database import db

all_profiles = db.reference('profiles').get() or {}

matches = []
for uid, data in all_profiles.items():
    if isinstance(data, dict):
        name = data.get('name', '').lower()
        if 'delstarford' in name or 'installer.py' in name:
            matches.append({
                'id': uid,
                'name': data.get('name', 'N/A'),
                'email': data.get('email', 'N/A'),
                'created_at': data.get('created_at', 'N/A')
            })

print("="*50)
print(f"Found {len(matches)} matching users:")
print("="*50)
for idx, m in enumerate(matches):
    print(f"[{idx+1}] ID: {m['id']}")
    print(f"    Name: {m['name']}")
    print(f"    Email: {m['email']}")
    print(f"    Created: {m['created_at']}")
    print("-" * 50)
