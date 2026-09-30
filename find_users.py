import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from app.database import db

users = db.reference('profiles').get() or {}
emails_to_find = [
    'omondidelstarford@gmail.com', 
    'info@delstarfordwords.co.ke', 
    'info@delstarfordworks.co.ke', 
    'info@fardcbo.org'
]

found = []
for uid, data in users.items():
    if isinstance(data, dict):
        name = data.get('name', '').lower()
        email = data.get('email', '').lower()
        if 'delstarford' in name or email in emails_to_find:
            found.append(data)

print(f"Found {len(found)} users:")
for user in found:
    print(f"Name: {user.get('name')}, Email: {user.get('email')}, Reg: {user.get('reg_number')}, Phone: {user.get('phone')}")
