import os
import sys
from datetime import datetime, timedelta, timezone
import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Define East Africa Time (UTC+3) for accurate timestamps
EAT = timezone(timedelta(hours=3))

# ==========================================
# 1. CONNECT TO FIREBASE
# ==========================================
CREDENTIALS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'firebase_key.json'))
DATABASE_URL = os.getenv("FIREBASE_DB_URL", "https://mmust-dating-site-default-rtdb.firebaseio.com/")

def initialize_firebase():
    if not firebase_admin._apps:
        try:
            if not os.path.exists(CREDENTIALS_PATH):
                print(f"❌ ERROR: Cannot find firebase_key.json at {CREDENTIALS_PATH}")
                print("Make sure the key file is in the same folder as this script.")
                sys.exit(1)

            cred = credentials.Certificate(CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
            print("🔗 Successfully connected to Firebase database.")
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            sys.exit(1)

# ==========================================
# 2. THE UNLOCK FUNCTION (MERCHANT)
# ==========================================
def grant_merchant_access(email_address):
    """Searches for a business by email and activates their subscription."""
    email_clean = email_address.strip().lower()
    print(f"\n🔍 Searching database for merchant email: {email_clean}...")
    
    try:
        restaurants_ref = db.reference('restaurants')
        
        # ⚡ UPGRADE: Use Firebase's built-in query for efficiency
        # This is much faster than downloading the entire 'restaurants' node
        matching_merchants = restaurants_ref.order_by_child('email').equal_to(email_clean).get()
        
        if matching_merchants:
            for matched_id, matched_data in matching_merchants.items():
                business_name = matched_data.get('business_name', 'Unknown Business')
                
                # Calculate expiry date (30 days from now in EAT)
                now_eat = datetime.now(EAT)
                expiry_date = (now_eat + timedelta(days=30)).isoformat()
                
                # Flip the switch!
                restaurants_ref.child(matched_id).update({
                    'subscription_active': True,
                    'subscription_start': now_eat.isoformat(),
                    'subscription_expiry': expiry_date,
                    'last_payment_receipt': 'GOD_MODE_MERCHANT_PASS'
                })
                
                print(f"\n🏪 Found Business: {business_name} (ID: {matched_id})")
                print(f"✅ SUCCESS: Merchant account activated!")
                print(f"📅 Subscription valid until: {expiry_date[:10]}")
        else:
            print(f"\n❌ ERROR: Could not find any merchant account registered with '{email_clean}'.")
            print("Make sure you typed the exact email used to register the business.")
            
    except Exception as e:
        print(f"\n❌ Database Error: {e}")

# ==========================================
# 3. RUN THE SCRIPT
# ==========================================
if __name__ == "__main__":
    print("\n======================================")
    print(" 🏪 MERCHANT VIP UNLOCK TOOL ")
    print("======================================")
    
    initialize_firebase()
    
    while True:
        target_email = input("\nEnter the MERCHANT EMAIL ADDRESS to unlock (or type 'exit' to quit): ").strip()
        
        if target_email.lower() in ['exit', 'quit', 'q']:
            print("Exiting tool. Goodbye!")
            break
        elif target_email:
            grant_merchant_access(target_email)
        else:
            print("Please enter a valid email address.")