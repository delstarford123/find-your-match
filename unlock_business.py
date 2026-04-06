import os
import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

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
            cred = credentials.Certificate(CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
            print("🔗 Connected to Firebase database.")
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            exit(1)

# ==========================================
# 2. THE UNLOCK FUNCTION (MERCHANT)
# ==========================================
def grant_merchant_access(email_address):
    """Searches for a business by email and activates their subscription."""
    email_clean = email_address.strip().lower()
    print(f"\n🔍 Searching for merchant account with email: {email_clean}...")
    
    try:
        restaurants_ref = db.reference('restaurants')
        
        # Fetch all restaurants to find the match safely
        all_restaurants = restaurants_ref.get() or {}
        
        matched_id = None
        matched_data = None
        
        for r_id, r_data in all_restaurants.items():
            if isinstance(r_data, dict) and r_data.get('email') == email_clean:
                matched_id = r_id
                matched_data = r_data
                break
        
        if matched_data:
            business_name = matched_data.get('business_name', 'Unknown Business')
            
            # Calculate expiry date (30 days from now, mimicking M-Pesa logic)
            now_eat = datetime.now(EAT)
            expiry_date = (now_eat + timedelta(days=30)).isoformat()
            
            # Flip the switch!
            restaurants_ref.child(matched_id).update({
                'subscription_active': True,
                'subscription_start': now_eat.isoformat(),
                'subscription_expiry': expiry_date,
                'last_payment_receipt': 'BYPASS_SCRIPT_TEST'
            })
            
            print(f"🏪 Found Business: {business_name} (ID: {matched_id})")
            print(f"✅ SUCCESS: Merchant bypassed paywall!")
            print(f"📅 Subscription extended to: {expiry_date}")
        else:
            print(f"❌ ERROR: Could not find any merchant account registered with '{email_clean}'.")
            print("Make sure you typed the exact email you used to register the business.")
            
    except Exception as e:
        print(f"Database error: {e}")

# ==========================================
# 3. RUN THE SCRIPT
# ==========================================
if __name__ == "__main__":
    print("======================================")
    print(" 🏪 MERCHANT VIP UNLOCK TOOL ")
    print("======================================")
    
    initialize_firebase()
    
    target_email = input("\nEnter the MERCHANT EMAIL ADDRESS to unlock: ")
    
    if target_email.strip():
        grant_merchant_access(target_email)
    else:
        print("Operation cancelled.")