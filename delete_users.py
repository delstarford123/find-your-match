import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from app.database import db, delete_user_account

users = db.reference('profiles').get() or {}
emails_to_find = [
    'omondidelstarford@gmail.com', 
    'info@delstarfordwords.co.ke', 
    'info@delstarfordworks.co.ke', 
    'info@fardcbo.org'
]

count = 0
for uid, data in users.items():
    if isinstance(data, dict):
        name = data.get('name', '').lower()
        email = data.get('email', '').lower()
        
        # Condition to find the users (same as before)
        if 'delstarford' in name or email in emails_to_find:
            # Check the exception condition
            if email != 'delstarfordisaiah@gmail.com':
                print(f"Deleting user: {data.get('name')} ({email}) - ID: {uid}")
                success = delete_user_account(uid)
                if success:
                    count += 1
                else:
                    print(f"Failed to delete {email}")

print(f"Successfully deleted {count} users.")
