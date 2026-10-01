import sys
import firebase_admin
from firebase_admin import credentials, db
import app.database

sys.stdout.reconfigure(encoding='utf-8')
app.database.initialize_firebase()

settings = db.reference('system_settings').get() or {}
print('System Settings Merchant Fee:', settings.get('merchant_fee'))

restaurants = db.reference('restaurants').get() or {}
print(f"Total merchants: {len(restaurants)}")
for k, v in list(restaurants.items())[-5:]: # Check last 5 merchants
    if isinstance(v, dict):
        print(f"Merchant {v.get('business_name')}: active={v.get('subscription_active')}, expiry={v.get('subscription_expiry')}")
